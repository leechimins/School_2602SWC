"""모델 호출. 진짜 API를 부르지 않는다.

여기서 지켜야 할 것은 하나다 — **무슨 일이 있어도 None을 돌려줄 뿐 예외를
올리지 않는다.** 그게 깨지면 시연 중 네트워크가 끊기는 순간 핵심 화면이
500으로 죽는다.
"""

from __future__ import annotations

import httpx
import pytest

from app.shared import llm


@pytest.fixture(autouse=True)
def 키를_심는다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.delenv("LLM_ENABLED", raising=False)


def _응답(status: int = 200, content: str = "{}") -> httpx.Response:
    return httpx.Response(
        status,
        json={"choices": [{"message": {"content": content}}]},
        request=httpx.Request("POST", "https://example.test/chat/completions"),
    )


def _보내면(monkeypatch: pytest.MonkeyPatch, 결과) -> None:
    def 가짜(*args, **kw):
        if isinstance(결과, Exception):
            raise 결과
        return 결과

    monkeypatch.setattr(llm.httpx, "post", 가짜)


# ── 스위치 ──────────────────────────────────────────────────────────


def test_키가_없으면_꺼진다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert llm.enabled() is False
    assert llm.complete_json("아무거나") is None


def test_키가_있으면_켜진다() -> None:
    assert llm.enabled() is True


def test_LLM_ENABLED_false면_꺼진다(monkeypatch: pytest.MonkeyPatch) -> None:
    """키가 있어도 끌 수 있어야 한다 — 시연 리허설에서 쓴다."""
    monkeypatch.setenv("LLM_ENABLED", "false")
    assert llm.enabled() is False
    assert llm.complete_json("아무거나") is None


def test_Gemini_이름으로도_읽는다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    assert llm.enabled() is True


# ── 실패해도 None ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "일어난_일",
    [
        httpx.ConnectError("네트워크 끊김"),
        httpx.ReadTimeout("20초 초과"),
        RuntimeError("예상 못 한 것"),
    ],
)
def test_호출이_실패하면_None(
    monkeypatch: pytest.MonkeyPatch, 일어난_일: Exception
) -> None:
    _보내면(monkeypatch, 일어난_일)
    assert llm.complete_json("아무거나") is None


@pytest.mark.parametrize("status", [401, 429, 500, 503])
def test_에러_응답이면_None(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    """429는 무료 한도를 넘긴 경우다. 시연 중에 충분히 일어난다."""
    _보내면(monkeypatch, _응답(status))
    assert llm.complete_json("아무거나") is None


# ── JSON 파싱 ───────────────────────────────────────────────────────


def test_그냥_JSON을_읽는다(monkeypatch: pytest.MonkeyPatch) -> None:
    _보내면(monkeypatch, _응답(content='{"utterances": [{"text": "좋아요"}]}'))
    assert llm.complete_json("x") == {"utterances": [{"text": "좋아요"}]}


@pytest.mark.parametrize(
    "감싼_것",
    [
        '```json\n{"a": 1}\n```',
        '```\n{"a": 1}\n```',
        '  ```json\n{"a": 1}\n```  ',
    ],
)
def test_코드_블록_울타리를_벗긴다(
    monkeypatch: pytest.MonkeyPatch, 감싼_것: str
) -> None:
    """모델이 ```json으로 감싸는 일이 흔하다."""
    _보내면(monkeypatch, _응답(content=감싼_것))
    assert llm.complete_json("x") == {"a": 1}


@pytest.mark.parametrize(
    "나쁜_것",
    [
        "",
        "JSON이 아닌 한국어 문장입니다",
        '{"깨진": ',
        "[1, 2, 3]",  # 배열은 거절한다 — 객체만 받는다
        "42",
        "null",
    ],
)
def test_읽을_수_없으면_None(
    monkeypatch: pytest.MonkeyPatch, 나쁜_것: str
) -> None:
    _보내면(monkeypatch, _응답(content=나쁜_것))
    assert llm.complete_json("x") is None


def test_응답_모양이_다르면_None(monkeypatch: pytest.MonkeyPatch) -> None:
    """공급자를 바꿨을 때 choices가 없는 응답이 올 수 있다."""
    _보내면(
        monkeypatch,
        httpx.Response(
            200,
            json={"error": {"message": "모델 이름이 틀렸습니다"}},
            request=httpx.Request("POST", "https://example.test/x"),
        ),
    )
    assert llm.complete_json("x") is None
