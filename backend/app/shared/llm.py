"""모델 호출이 일어나는 유일한 곳.

키·주소·타임아웃·JSON 파싱·끄는 스위치가 여기 모인다. 조율의 발언과
회의록 요약이 같은 함수를 쓴다 — 두 번 짜면 실패 처리가 두 군데서 달라진다.

**실패하면 None을 돌려준다.** 예외를 올리지 않는 게 설계의 핵심이다. 키가
없어도, 공급자가 죽어도, 응답이 깨져도 앱은 끝까지 돈다. 부르는 쪽이
None을 받으면 준비된 문장으로 떨어진다 — 브리프의 "서버·AI가 실패해도
준비된 데이터로 그대로 이어 갑니다"가 그 길이다.

공급자를 코드에 박지 않는다. OpenAI 호환 Chat Completions 규약만 맞추면
Gemini·Groq·OpenRouter가 환경변수 두 줄로 바뀐다. 기본값은 Gemini다.
"""

from __future__ import annotations

import base64
import json
import os
import re

import httpx
from dotenv import load_dotenv

load_dotenv()

# Gemini의 OpenAI 호환 엔드포인트. 끝의 openai/ 가 있어야 한다.
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_MODEL = "gemini-3.8-flash"

# 조율 한 라운드는 20초 안에 끝나야 한다. 브리프가 "시간 정하는 과정"을
# 10~20초로 잡았고, 그걸 넘으면 구경거리가 기다림이 된다.
TIMEOUT_SEC = 20.0

# 모델이 ```json 울타리로 감싸는 일이 흔하다. 벗겨 내고 파싱한다.
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def _api_key() -> str | None:
    """공급자 중립인 이름을 먼저 보고, 없으면 Gemini 이름을 본다.

    윈도우는 환경변수 이름의 대소문자를 안 가려서 .env에 Gemini_API_Key로
    적어도 읽힌다. 리눅스는 가린다 — 배포 전에 대문자로 통일해야 한다.
    """
    return os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY")


def enabled() -> bool:
    """키가 있으면 켜진다. LLM_ENABLED=false로만 끈다.

    켜려고 변수를 하나 더 채우게 하지 않는다 — 키를 넣었는데 스위치를
    안 켜서 "왜 안 되지"로 시간을 쓰는 일이 가장 흔하다.
    """
    if os.getenv("LLM_ENABLED", "").strip().lower() == "false":
        return False
    return bool(_api_key())


def complete_json(prompt: str, *, max_tokens: int = 700) -> dict | None:
    """프롬프트를 보내고 JSON 객체를 받는다. 안 되면 None.

    response_format(JSON 모드)을 쓰지 않는다. Gemini의 OpenAI 호환 층이
    그걸 문서화하지 않았고(Pydantic .parse만 적혀 있다), 공급자를 바꿀 때
    또 깨진다. 대신 프롬프트로 JSON을 요구하고 방어적으로 파싱한다.
    """
    key = _api_key()
    if not enabled() or key is None:
        return None

    base = os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    try:
        response = httpx.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": os.getenv("LLM_MODEL", DEFAULT_MODEL),
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                # 같은 입력에 같은 답을 주게 한다. 리허설과 본 시연이
                # 어긋나는 것을 조금이라도 줄인다.
                "temperature": 0.3,
                # 추론을 끈다. 판단은 이미 계산으로 끝났고 모델이 할 일은
                # 그 결과를 문장으로 옮기는 것뿐이다.
                #
                # 끄지 않으면 추론 토큰이 max_tokens를 먹는다. 실제로 라운드
                # 프롬프트에서 추론 1377 + 출력 43으로 잘려 content가 중간에
                # 끊겼고, 파싱이 실패해 늘 템플릿으로 떨어졌다. 조용히
                # 떨어지므로 발언을 눈으로 읽어 보기 전까지 몰랐다.
                #
                # 추론을 끈 뒤 4명 라운드의 실제 출력은 324 토큰이다. 기본
                # 상한 700은 그 두 배가 조금 넘는다 — 6명이어도 남고, 모델이
                # 장황해지면 잘려서 템플릿으로 떨어진다(앱은 계속 돈다).
                "reasoning_effort": "none",
            },
            timeout=TIMEOUT_SEC,
        )
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"]
    except Exception:  # noqa: BLE001 - 무엇이 실패해도 앱은 돌아야 한다
        return None

    return _parse(text)


# 녹음 받아적기(레인 B, #40). 70초 녹음에 8초 안팎이었고(11/8 측정), 30분까지
# 받으므로 넉넉히 둔다. 조율처럼 구경하는 시간이 아니라 "정리 중"을 기다리는 시간이다.
AUDIO_TIMEOUT_SEC = 120.0


def complete_json_audio(
    prompt: str, audio: bytes, *, audio_format: str = "mp3", max_tokens: int = 16_000
) -> dict | None:
    """프롬프트와 녹음을 함께 보내고 JSON 객체를 받는다. 안 되면 None.

    complete_json과 같은 주소·키·끄는 스위치·실패 규칙을 쓴다. OpenAI 호환
    규약의 input_audio라 형식은 mp3·wav만 된다 — 변환은 부르는 쪽이 한다.
    녹음은 보내고 버린다(저장하지 않음).
    """
    key = _api_key()
    if not enabled() or key is None:
        return None

    base = os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    try:
        response = httpx.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": os.getenv("LLM_MODEL", DEFAULT_MODEL),
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "input_audio",
                                "input_audio": {
                                    "data": base64.b64encode(audio).decode("ascii"),
                                    "format": audio_format,
                                },
                            },
                        ],
                    }
                ],
                "max_tokens": max_tokens,
                # 받아적기는 들은 그대로 옮기는 일이라 흔들림이 없어야 한다
                "temperature": 0,
                "reasoning_effort": "none",
            },
            timeout=AUDIO_TIMEOUT_SEC,
        )
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"]
    except Exception:  # noqa: BLE001 - 무엇이 실패해도 앱은 돌아야 한다
        return None

    return _parse(text)


def _parse(text: str) -> dict | None:
    """울타리를 벗기고 JSON 객체만 받는다. 배열이나 숫자는 거절한다."""
    if not text:
        return None
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None
