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


# ── 조각 쌓기 ────────────────────────────────────────────────────────


def _seg(seq: int, text: str | None = None, label: str | None = "A") -> dict:
    return {"seq": seq, "speaker_label": label, "text": text or f"{seq}번째 말"}


def _send(client: TestClient, room: Room, meeting: Meeting, *segs: dict):
    return client.post(_url(room, meeting, "/transcript/segments"), json={"segments": list(segs)})


def _lines(client: TestClient, room: Room, meeting: Meeting) -> list[tuple]:
    body = client.get(f"{API}/rooms/{room.id}/meetings/{meeting.id}").json()
    return [(line["seq"], line["speaker_label"], line["text"]) for line in body["transcript"]]


def test_조각이_번호와_라벨로_쌓인다(client, seeded, room, blank):
    _start(client, room, blank)

    res = _send(client, room, blank, _seg(0, "안녕하세요"), _seg(1, "발표는 제가 할게요", "B"))

    assert res.status_code == 200, res.text
    assert res.json() == {"added": 2, "skipped": 0, "last_seq": 1, "missing": []}
    assert _lines(client, room, blank) == [
        (0, "A", "안녕하세요"),
        (1, "B", "발표는 제가 할게요"),
    ]


def test_같은_번호를_다시_보내면_건너뛰고_처음_것이_남는다(client, seeded, room, blank):
    _start(client, room, blank)
    _send(client, room, blank, _seg(0, "처음"), _seg(1))

    # 끊겼다고 보고 같은 조각을 다시 보낸다(글자가 조금 달라도 처음 것이 남는다)
    res = _send(client, room, blank, _seg(0, "다시"), _seg(1), _seg(2))

    assert res.json() == {"added": 1, "skipped": 2, "last_seq": 2, "missing": []}
    lines = _lines(client, room, blank)
    assert [seq for seq, *_ in lines] == [0, 1, 2]
    assert lines[0][2] == "처음"


def test_한_요청_안의_같은_번호도_한_번만_쌓인다(client, seeded, room, blank):
    _start(client, room, blank)

    res = _send(client, room, blank, _seg(0, "앞"), _seg(0, "뒤"))

    assert res.json()["added"] == 1
    assert _lines(client, room, blank) == [(0, "A", "앞")]


def test_빠진_번호를_알려_주고_채우면_비워진다(client, seeded, room, blank):
    _start(client, room, blank)

    res = _send(client, room, blank, _seg(0), _seg(3), _seg(5))
    assert res.json()["missing"] == [1, 2, 4]
    assert res.json()["last_seq"] == 5

    res = _send(client, room, blank, _seg(4), _seg(2), _seg(1))
    assert res.json()["missing"] == []


def test_순서가_섞여_와도_원문은_번호_순이다(client, seeded, room, blank):
    _start(client, room, blank)

    _send(client, room, blank, _seg(2, "셋"), _seg(0, "하나"))
    _send(client, room, blank, _seg(1, "둘"))

    assert [text for *_, text in _lines(client, room, blank)] == ["하나", "둘", "셋"]


def test_라벨이_없어도_된다(client, seeded, room, blank):
    _start(client, room, blank)

    _send(client, room, blank, _seg(0, "누군지 모름", label=None))

    assert _lines(client, room, blank) == [(0, None, "누군지 모름")]


def test_시작_전에는_조각을_못_올린다(client, seeded, room, blank):
    res = _send(client, room, blank, _seg(0))

    assert res.status_code == 409
    assert res.json()["code"] == "NOT_RECORDING"


@pytest.mark.parametrize(
    "seg",
    [
        {"seq": -1, "text": "음수 번호"},
        {"seq": 0, "text": ""},
        {"seq": 0, "text": "라벨이 김", "speaker_label": "가나다라마바사아자"},
    ],
)
def test_잘못된_조각은_400이다(client, seeded, room, blank, seg):
    _start(client, room, blank)

    res = _send(client, room, blank, seg)

    assert res.status_code == 400


# ── 멈추기 ───────────────────────────────────────────────────────────


def _stop(client: TestClient, room: Room, meeting: Meeting):
    return client.post(_url(room, meeting, "/recording/stop"))


def test_멈추면_원문은_남고_상태가_멈춤이_된다(client, seeded, room, blank):
    _start(client, room, blank)
    _send(client, room, blank, _seg(0, "하나"), _seg(1, "둘"))
    stop_at = datetime(2026, 11, 10, 16, 0, tzinfo=KST)
    demo_clock.set_clock(seeded, stop_at)
    seeded.commit()

    res = _stop(client, room, blank)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["recording_state"] == "stopped"
    assert [line["text"] for line in body["transcript"]] == ["하나", "둘"]
    assert body["minutes"] is None  # 요약은 따로 부른다
    seeded.refresh(blank)
    assert blank.recording_stopped_at == stop_at


def test_두_번_멈춰도_그대로다(client, seeded, room, blank):
    _start(client, room, blank)
    _stop(client, room, blank)
    seeded.refresh(blank)
    first = blank.recording_stopped_at
    demo_clock.set_clock(seeded, datetime(2026, 11, 10, 17, 0, tzinfo=KST))
    seeded.commit()

    res = _stop(client, room, blank)

    assert res.status_code == 200
    seeded.refresh(blank)
    assert blank.recording_stopped_at == first


def test_시작_전에는_멈출_수_없다(client, seeded, room, blank):
    res = _stop(client, room, blank)

    assert res.status_code == 409
    assert res.json()["code"] == "NOT_RECORDING"


def test_멈춘_뒤에는_조각도_다시_시작도_안_된다(client, seeded, room, blank):
    _start(client, room, blank)
    _send(client, room, blank, _seg(0))
    _stop(client, room, blank)

    late = _send(client, room, blank, _seg(1))
    again = _start(client, room, blank)

    assert late.status_code == 409
    assert late.json() == {"code": "RECORDING_STOPPED", "message": "이미 받아적기를 마쳤어요."}
    assert again.status_code == 409
    assert again.json()["code"] == "RECORDING_STOPPED"
    assert [seq for seq, *_ in _lines(client, room, blank)] == [0]


# ── 받아적는 동안 막기 ───────────────────────────────────────────────


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """요약 모델을 가짜로. 받은 프롬프트를 남긴다."""
    from app.minutes import summarize

    prompts: list[str] = []

    def request(prompt: str) -> dict:
        prompts.append(prompt)
        return {
            "headline": "발표 역할 나눔",
            "decisions": [{"text": "발표는 민지가 맡는다", "lines": [1]}],
            "discussions": [],
            "pendings": [],
            "tasks": [{"title": "슬라이드 만들기", "assignee": "민지", "due_date": None, "lines": [1]}],
        }

    monkeypatch.setattr(summarize, "request", request)
    return prompts


def test_받아적는_중에는_직접_쓰기가_막힌다(client, seeded, room, blank):
    _start(client, room, blank)
    _send(client, room, blank, _seg(0, "받아적은 말"))

    res = client.put(_url(room, blank, "/transcript"), json={"text": "지수: 덮어쓰기"})

    assert res.status_code == 409
    assert res.json() == {"code": "RECORDING", "message": "받아적는 중이에요. 멈춘 뒤에 해 주세요."}
    assert _lines(client, room, blank) == [(0, "A", "받아적은 말")]


def test_받아적는_중에는_요약이_막히고_모델을_안_부른다(client, seeded, room, blank, model):
    _start(client, room, blank)
    _send(client, room, blank, _seg(0))

    res = client.post(_url(room, blank, "/summarize"))

    assert res.status_code == 409
    assert res.json()["code"] == "RECORDING"
    assert model == []


def test_멈춘_뒤에는_요약이_되고_직접_쓰기로_고칠_수_있다(client, seeded, room, blank, model):
    _start(client, room, blank)
    _send(client, room, blank, _seg(0, "시작해요", "A"), _seg(1, "발표는 제가 할게요", "B"))
    _stop(client, room, blank)

    summarized = client.post(_url(room, blank, "/summarize"))
    assert summarized.status_code == 200, summarized.text
    assert "[1] (모름): 발표는 제가 할게요" in model[0]

    fixed = client.put(_url(room, blank, "/transcript"), json={"text": "지수: 시작해요\n민지: 발표는 제가 할게요"})
    assert fixed.status_code == 200
    body = fixed.json()
    assert body["transcript_mode"] == "manual"
    assert [line["speaker_name"] for line in body["transcript"]] == ["지수", "민지"]
