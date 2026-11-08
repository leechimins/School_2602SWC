"""받아적기(STT) — 시작·조각 쌓기·멈추기·말한 사람 정하기.

엔진은 쓰지 않는다. 서버는 글자 조각만 받으므로 테스트가 브라우저 대신
조각을 보낸다. 시드의 10/27 "역할 나누기"(원문 없음)로 받아적고,
10/31 "중간 발표 자료 나누기"(직접 쓴 원문 6줄)는 섞이면 안 되는 쪽으로 쓴다.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.meeting.models import Meeting
from app.shared import demo_clock
from app.shared.base import KST
from app.shared.enums import MeetingStatus, Mode
from app.shared.models import Room, User

API = "/api/v1"
NOW = datetime(2026, 11, 10, 15, 0, tzinfo=KST)


@pytest.fixture
def room(seeded: Session, login) -> Room:
    demo_clock.set_clock(seeded, NOW)
    seeded.commit()
    login("지수")
    return seeded.exec(select(Room)).one()


def _meeting(session: Session, topic: str) -> Meeting:
    return session.exec(select(Meeting).where(Meeting.topic == topic)).one()


def _user(session: Session, name: str) -> User:
    return session.exec(select(User).where(User.name == name)).one()


def _url(room: Room, meeting: Meeting, path: str) -> str:
    return f"{API}/rooms/{room.id}/meetings/{meeting.id}{path}"


def _start(client: TestClient, room: Room, meeting: Meeting):
    return client.post(_url(room, meeting, "/recording/start"))


@pytest.fixture
def blank(seeded: Session) -> Meeting:
    """원문이 없는 지난 회의."""
    return _meeting(seeded, "역할 나누기")


# ── 시작 ─────────────────────────────────────────────────────────────


def test_시작하면_받아적는_중이_되고_시각은_시연_시계다(client, seeded, room, blank):
    res = _start(client, room, blank)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["transcript_mode"] == "stt"
    assert body["recording_state"] == "recording"
    assert body["transcript"] == []
    seeded.refresh(blank)
    assert blank.recording_started_at == NOW


def test_받아적는_중에_다시_눌러도_그대로다(client, seeded, room, blank):
    _start(client, room, blank)
    demo_clock.set_clock(seeded, datetime(2026, 11, 10, 15, 30, tzinfo=KST))
    seeded.commit()

    res = _start(client, room, blank)

    assert res.status_code == 200
    assert res.json()["recording_state"] == "recording"
    seeded.refresh(blank)
    assert blank.recording_started_at == NOW  # 처음 시각 그대로


def test_직접_쓴_원문이_있으면_시작할_수_없다(client, seeded, room):
    written = _meeting(seeded, "중간 발표 자료 나누기")

    res = _start(client, room, written)

    assert res.status_code == 409
    assert res.json() == {"code": "TRANSCRIPT_EXISTS", "message": "이미 직접 쓴 원문이 있어요."}
    seeded.refresh(written)
    assert written.transcript_mode == "manual"


@pytest.mark.parametrize("status", [MeetingStatus.PROPOSED, MeetingStatus.CANCELLED])
def test_확정_전이나_취소된_회의는_받아적을_수_없다(client, seeded, room, status):
    meeting = Meeting(
        room_id=room.id,
        topic="조율 중",
        start_at=datetime(2026, 11, 12, 14, tzinfo=KST),
        end_at=datetime(2026, 11, 12, 16, tzinfo=KST),
        mode=Mode.ONLINE,
        status=status,
    )
    seeded.add(meeting)
    seeded.commit()

    res = _start(client, room, meeting)

    assert res.status_code == 409
    assert res.json()["code"] == "NOT_CONFIRMED"


def test_직접_쓴_회의록의_줄은_라벨이_없고_상태는_none이다(client, seeded, room):
    written = _meeting(seeded, "중간 발표 자료 나누기")

    body = client.get(f"{API}/rooms/{room.id}/meetings/{written.id}").json()

    assert body["recording_state"] == "none"
    assert all(line["speaker_label"] is None for line in body["transcript"])
