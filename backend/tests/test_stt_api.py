"""받아적기 녹음 올리기 — 녹음 파일을 Gemini로 받아적어 원문으로.

모델(llm.complete_json_audio)은 가짜로 바꾼다. 녹음 변환(PyAV)은 진짜로 돈다 —
테스트 안에서 짧은 소리를 만들어 보낸다.
"""

from __future__ import annotations

import io
import math
import struct
import wave
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.meeting.models import Meeting
from app.minutes import stt
from app.shared import demo_clock, llm
from app.shared.base import KST
from app.shared.models import Room

API = "/api/v1"
NOW = datetime(2026, 11, 10, 15, 0, tzinfo=KST)
STOP = datetime(2026, 11, 10, 15, 30, tzinfo=KST)

ENGINE_LINES = [
    {"speaker": "화자1", "text": "오늘은 발표 순서를 정해요."},
    {"speaker": "화자2", "text": "도입은 제가 할게요. 금요일까지 대본 써 올게요."},
    {"speaker": "화자1", "text": "리허설은 다음 주 월요일에 해요."},
    {"speaker": None, "text": "누가 말했는지 모름"},
]


def _wav(seconds: float = 1.0, *, rate: int = 16_000) -> bytes:
    """짧은 삐 소리 wav(표준 라이브러리로). 실제 변환 길을 타게 한다."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        n = int(seconds * rate)
        out.writeframes(
            b"".join(
                struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate)))
                for i in range(n)
            )
        )
    return buf.getvalue()


@pytest.fixture
def room(seeded: Session, login) -> Room:
    demo_clock.set_clock(seeded, NOW)
    seeded.commit()
    login("지수")
    return seeded.exec(select(Room)).one()


@pytest.fixture
def blank(seeded: Session) -> Meeting:
    return seeded.exec(select(Meeting).where(Meeting.topic == "역할 나누기")).one()


class Engine:
    def __init__(self) -> None:
        self.reply: dict | None = {"lines": ENGINE_LINES}
        self.calls: list[tuple[str, bytes, str]] = []
        self.during = None  # 받아적는 사이 일어날 일

    def __call__(self, prompt: str, audio: bytes, *, audio_format: str = "mp3", **_) -> dict | None:
        self.calls.append((prompt, audio, audio_format))
        if self.during:
            self.during()
        return self.reply


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> Engine:
    fake = Engine()
    monkeypatch.setattr(llm, "complete_json_audio", fake)
    return fake


def _url(room: Room, meeting: Meeting, path: str) -> str:
    return f"{API}/rooms/{room.id}/meetings/{meeting.id}{path}"


def _start(client: TestClient, room: Room, meeting: Meeting) -> None:
    assert client.post(_url(room, meeting, "/recording/start")).status_code == 200


def _upload(client: TestClient, room: Room, meeting: Meeting, data: bytes | None = None):
    return client.post(
        _url(room, meeting, "/recording/audio"),
        content=_wav() if data is None else data,
        headers={"Content-Type": "audio/wav"},
    )


def _state(client: TestClient, room: Room, meeting: Meeting) -> str:
    return client.get(f"{API}/rooms/{room.id}/meetings/{meeting.id}").json()["recording_state"]


# ── 정상 ─────────────────────────────────────────────────────────────


def test_녹음을_받아적어_줄과_목소리_라벨로_쌓고_멈춘다(client, seeded, room, blank, engine):
    _start(client, room, blank)
    demo_clock.set_clock(seeded, STOP)
    seeded.commit()

    res = _upload(client, room, blank)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["recording_state"] == "stopped"
    assert [(line["seq"], line["speaker_label"], line["text"]) for line in body["transcript"]] == [
        (0, "A", "오늘은 발표 순서를 정해요."),
        (1, "B", "도입은 제가 할게요. 금요일까지 대본 써 올게요."),
        (2, "A", "리허설은 다음 주 월요일에 해요."),
        (3, None, "누가 말했는지 모름"),
    ]
    seeded.refresh(blank)
    assert blank.recording_stopped_at == STOP


def test_엔진에는_mp3와_팀원_이름이_간다(client, seeded, room, blank, engine):
    _start(client, room, blank)

    _upload(client, room, blank)

    prompt, audio, fmt = engine.calls[0]
    assert fmt == "mp3"
    assert audio[:3] == b"ID3" or audio[:2] == b"\xff\xfb" or audio[0] == 0xFF  # mp3 머리
    for name in ("지수", "민지", "현우", "서연"):
        assert name in prompt


def test_올린_뒤_말한_사람을_정할_수_있다(client, seeded, room, blank, engine):
    from app.shared.models import User

    _start(client, room, blank)
    _upload(client, room, blank)
    minji = seeded.exec(select(User).where(User.name == "민지")).one()

    res = client.put(_url(room, blank, "/speaker-mapping"), json={"labels": {"B": minji.id}})

    assert [line["speaker_name"] for line in res.json()["transcript"]] == [None, "민지", None, None]


# ── 실패해도 받아적는 중 그대로 ──────────────────────────────────────


def test_깨진_파일은_400이고_엔진을_안_부른다(client, seeded, room, blank, engine):
    _start(client, room, blank)

    res = _upload(client, room, blank, b"this is not audio")

    assert res.status_code == 400
    assert res.json() == {"code": "AUDIO_INVALID", "message": "녹음 파일을 읽지 못했어요. 직접 입력해 주세요."}
    assert engine.calls == []
    assert _state(client, room, blank) == "recording"


def test_너무_긴_녹음은_400이다(client, seeded, room, blank, engine, monkeypatch):
    monkeypatch.setattr(stt, "MAX_SECONDS", 0.5)
    _start(client, room, blank)

    res = _upload(client, room, blank, _wav(1.0))

    assert res.status_code == 400
    assert res.json()["code"] == "AUDIO_TOO_LONG"
    assert engine.calls == []


def test_너무_큰_파일은_400이다(client, seeded, room, blank, engine, monkeypatch):
    monkeypatch.setattr(stt, "MAX_BYTES", 100)
    _start(client, room, blank)

    res = _upload(client, room, blank)

    assert res.json()["code"] == "AUDIO_TOO_LONG"


def test_말소리가_없으면_400이고_받아적는_중_그대로(client, seeded, room, blank, engine):
    engine.reply = {"lines": []}
    _start(client, room, blank)

    res = _upload(client, room, blank)

    assert res.status_code == 400
    assert res.json()["code"] == "NO_SPEECH"
    assert _state(client, room, blank) == "recording"


@pytest.mark.parametrize("reply", [None, {"text": "모양이 다름"}])
def test_AI가_실패하면_503이고_같은_녹음으로_다시_하면_된다(client, seeded, room, blank, engine, reply):
    engine.reply = reply
    _start(client, room, blank)

    failed = _upload(client, room, blank)

    assert failed.status_code == 503
    assert failed.json() == {"code": "AGENT_TIMEOUT", "message": "잠시 후 다시 해 주세요."}
    assert _state(client, room, blank) == "recording"

    engine.reply = {"lines": ENGINE_LINES}
    again = _upload(client, room, blank)
    assert again.status_code == 200
    assert len(again.json()["transcript"]) == 4


# ── 상태 ─────────────────────────────────────────────────────────────


def test_시작_전에는_못_올린다(client, seeded, room, blank, engine):
    res = _upload(client, room, blank)

    assert res.status_code == 409
    assert res.json()["code"] == "NOT_RECORDING"
    assert engine.calls == []


def test_이미_올려서_멈췄으면_다시_못_올린다(client, seeded, room, blank, engine):
    _start(client, room, blank)
    _upload(client, room, blank)

    res = _upload(client, room, blank)

    assert res.status_code == 409
    assert res.json()["code"] == "RECORDING_STOPPED"
    assert len(engine.calls) == 1


def test_글_조각으로_이미_쌓였으면_못_올린다(client, seeded, room, blank, engine):
    _start(client, room, blank)
    client.post(
        _url(room, blank, "/transcript/segments"),
        json={"segments": [{"seq": 0, "text": "먼저 온 글"}]},
    )

    res = _upload(client, room, blank)

    assert res.status_code == 409
    assert res.json()["code"] == "TRANSCRIPT_EXISTS"


def test_받아적는_사이_누가_멈췄으면_덮어쓰지_않는다(client, seeded, room, blank, engine):
    _start(client, room, blank)

    def someone_stops() -> None:
        blank.recording_stopped_at = STOP
        seeded.add(blank)
        seeded.commit()

    engine.during = someone_stops

    res = _upload(client, room, blank)

    assert res.status_code == 409
    assert res.json()["code"] == "RECORDING_STOPPED"
    body = client.get(f"{API}/rooms/{room.id}/meetings/{blank.id}").json()
    assert body["transcript"] == []


# ── 결과 다듬기 (단위) ───────────────────────────────────────────────


def test_화자는_나온_순서대로_A_B_C이고_빈_줄은_버린다():
    pieces = stt.parse(
        {
            "lines": [
                {"speaker": "화자3", "text": "첫 말"},
                {"speaker": "화자1", "text": "  "},
                {"speaker": "화자1", "text": "둘째 말"},
                {"speaker": 3, "text": "숫자 화자"},
                "엉뚱한 줄",
            ]
        }
    )
    assert [(p.seq, p.speaker_label, p.text) for p in pieces] == [
        (0, "A", "첫 말"),
        (1, "B", "둘째 말"),
        (2, "C", "숫자 화자"),
    ]
