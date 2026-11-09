"""녹음 받아적기 — Gemini로 녹음 파일을 원문 줄로. 레인 B (#40).

엔진은 Gemini(`shared/llm.py`의 complete_json_audio). 고른 이유와 대안(CLOVA)은
`_local/STT-평가/STT-엔진-결정-전달용.md`. 엔진을 바꾸면 이 파일만 바꾼다 —
결과를 recording.Piece 목록으로 내면 쌓기·말한 사람 정하기·요약은 그대로다.

- 녹음을 멈출 때 파일 하나로 받는다. 조각마다 보내면 엔진이 화자 번호를
  조각마다 새로 매겨, 회의 전체에서 "화자1"이 같은 사람이라는 보장이 없다.
- 브라우저 녹음(webm/opus, Safari mp4/aac 등)을 mp3로 바꿔 보낸다. OpenAI 호환
  규약의 녹음은 mp3·wav만 되고, mp3가 작다(16kHz 모노 32kbps, 1분 약 240KB).
- 음성은 저장하지 않는다. 메모리에서 바꿔 보내고 버린다.
"""

from __future__ import annotations

import io
import string

from app.minutes.recording import Piece
from app.shared import llm

MAX_BYTES = 25 * 1024 * 1024
MAX_SECONDS = 30 * 60
MAX_LINES = 2000
_RATE = 16_000


class SttError(Exception):
    """받아적기 실패. 종류만 담는다."""


class AudioInvalid(SttError):
    """녹음 파일을 읽을 수 없다(깨짐, 모르는 형식, 소리 없음)."""


class AudioTooLong(SttError):
    """MAX_SECONDS나 MAX_BYTES를 넘는다."""


class NoSpeech(SttError):
    """엔진이 말소리를 하나도 못 찾았다."""


class EngineFailed(SttError):
    """엔진 실패·시간 초과·키 없음. 잠시 후 다시 하면 된다."""


def to_mp3(data: bytes) -> bytes:
    """녹음을 16kHz 모노 mp3로. 길이도 여기서 잰다."""
    import av  # 무거운 라이브러리라 받아적기를 부를 때만 읽는다

    if len(data) > MAX_BYTES:
        raise AudioTooLong("bytes")
    out_buf = io.BytesIO()
    samples = 0
    try:
        with av.open(io.BytesIO(data)) as src:
            if not src.streams.audio:
                raise AudioInvalid("no audio stream")
            with av.open(out_buf, "w", format="mp3") as dst:
                stream = dst.add_stream("libmp3lame", rate=_RATE, layout="mono")
                stream.bit_rate = 32_000
                resampler = av.AudioResampler(format="s16p", layout="mono", rate=_RATE)

                def write(frame) -> None:
                    for packet in stream.encode(frame):
                        dst.mux(packet)

                for frame in src.decode(audio=0):
                    for out in resampler.resample(frame):
                        samples += out.samples
                        if samples > MAX_SECONDS * _RATE:
                            raise AudioTooLong("seconds")
                        write(out)
                for out in resampler.resample(None):
                    samples += out.samples
                    write(out)
                write(None)
    except SttError:
        raise
    except Exception:  # noqa: BLE001 - av가 형식마다 다른 예외를 올린다
        raise AudioInvalid("decode") from None
    if samples == 0:
        raise AudioInvalid("empty")
    return out_buf.getvalue()


def build_prompt(member_names: list[str]) -> str:
    return f"""다음은 대학생 팀 프로젝트 회의 녹음이다. 들리는 그대로 한국어로 받아적는다.
- 말하는 사람이 바뀌면 줄을 나눈다. 목소리로 화자를 구분해 "화자1", "화자2"처럼 표시한다. 같은 목소리는 회의 내내 같은 번호.
- 팀원 이름은 {", ".join(member_names)}이다. 이름이 들리면 그 글자 그대로 적는다.
- 요일·날짜는 들린 말 그대로 적는다(숫자로 바꾸지 않는다).
- 고치거나 요약하지 않는다. 말소리가 없으면 lines를 빈 배열로 둔다.
JSON 하나만 출력한다: {{"lines": [{{"speaker": "화자1", "text": "발언"}}]}}"""


def parse(result: dict | None) -> list[Piece]:
    """엔진 결과 → 줄. 엔진의 화자 이름은 나온 순서대로 A, B, C…로 바꾼다.

    "목소리 A"처럼 화면에 보일 짧은 라벨이고 speaker_label 칸(8자)에 맞는다.
    26명을 넘는 화자나 이름 없는 화자는 라벨 없이 둔다(말한 사람 정하기에서 줄마다 고른다).
    """
    if result is None:
        raise EngineFailed("no result")
    raw = result.get("lines")
    if not isinstance(raw, list):
        raise EngineFailed("shape")

    labels: dict[str, str] = {}
    pieces: list[Piece] = []
    for item in raw[:MAX_LINES]:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        speaker = item.get("speaker")
        label = None
        if isinstance(speaker, str | int) and str(speaker).strip():
            key = str(speaker).strip()
            if key not in labels and len(labels) < len(string.ascii_uppercase):
                labels[key] = string.ascii_uppercase[len(labels)]
            label = labels.get(key)
        pieces.append(Piece(seq=len(pieces), speaker_label=label, text=text.strip()))
    if not pieces:
        raise NoSpeech("empty")
    return pieces


def transcribe(data: bytes, member_names: list[str]) -> list[Piece]:
    """녹음 → 원문 줄. AudioInvalid · AudioTooLong · NoSpeech · EngineFailed를 올린다."""
    mp3 = to_mp3(data)
    return parse(llm.complete_json_audio(build_prompt(member_names), mp3, audio_format="mp3"))
