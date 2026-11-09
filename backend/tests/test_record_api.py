"""Record 엔드포인트. 시드의 지난 회의 2건으로 본다.

- 10/27 "역할 나누기": 기록 없음
- 10/31 "중간 발표 자료 나누기": 원문 6줄, 회의록, 확정 할 일 5개, AI 제안 3개
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.meeting.models import Meeting
from app.minutes.models import Task
from app.minutes.transcript import parse
from app.shared import demo_clock
from app.shared.base import KST
from app.shared.enums import MeetingStatus, Mode
from app.shared.models import Room, User

API = "/api/v1"


def _room(session: Session) -> Room:
    return session.exec(select(Room)).one()


def _meeting(session: Session, topic: str) -> Meeting:
    return session.exec(select(Meeting).where(Meeting.topic == topic)).one()


def _url(room: Room, path: str = "") -> str:
    return f"{API}/rooms/{room.id}/meetings{path}"


# ── 목록 ────────────────────────────────────────────────────────────


def test_목록은_최근_회의가_먼저이고_기록_여부가_보인다(
    client: TestClient, seeded: Session, login
) -> None:
    login("민지")

    meetings = client.get(_url(_room(seeded))).json()["meetings"]

    assert [m["topic"] for m in meetings] == ["중간 발표 자료 나누기", "역할 나누기"]
    recent, old = meetings
    assert recent["headline"] == "중간 발표 자료를 역할별로 나눔"
    assert recent["has_transcript"] is True
    assert recent["suggestion_count"] == 3
    assert recent["attendees"] == ["지수", "민지", "현우", "서연"]
    assert old["headline"] is None
    assert old["has_transcript"] is False
    assert old["suggestion_count"] == 0


def test_회의안과_취소된_회의는_목록에_없다(
    client: TestClient, seeded: Session, login
) -> None:
    room = _room(seeded)
    for status in (MeetingStatus.PROPOSED, MeetingStatus.CANCELLED):
        seeded.add(
            Meeting(
                room_id=room.id,
                topic=f"안 나와야 함 {status}",
                start_at=datetime(2026, 11, 12, 14, tzinfo=KST),
                end_at=datetime(2026, 11, 12, 16, tzinfo=KST),
                mode=Mode.ONLINE,
                status=status,
            )
        )
    seeded.commit()
    login("지수")

    topics = [m["topic"] for m in client.get(_url(room)).json()["meetings"]]

    assert not any(t.startswith("안 나와야 함") for t in topics)


def test_팀원이_아니면_목록을_못_본다(
    client: TestClient, seeded: Session, login
) -> None:
    seeded.add(User(name="밖사람"))
    seeded.commit()
    login("밖사람")

    assert client.get(_url(_room(seeded))).status_code == 403


# ── 회의록 보기 ─────────────────────────────────────────────────────


def test_회의록에_원문_요약_할_일_제안이_다_온다(
    client: TestClient, seeded: Session, login
) -> None:
    room = _room(seeded)
    meeting = _meeting(seeded, "중간 발표 자료 나누기")
    login("현우")

    body = client.get(_url(room, f"/{meeting.id}")).json()

    assert [line["seq"] for line in body["transcript"]] == list(range(6))
    assert body["transcript"][0]["speaker_name"] == "지수"
    assert body["transcript"][-1]["speaker_user_id"] is None
    assert body["minutes"]["headline"] == "중간 발표 자료를 역할별로 나눔"
    assert len(body["minutes"]["decisions"]) == 2
    assert len(body["minutes"]["discussions"]) == 1
    assert len(body["minutes"]["pendings"]) == 2
    # 직접 추가한 할 일은 출처 회의가 없어 여기 안 나온다.
    # "참고 사례 조사"는 10/27 회의에서 나와 여기서 끝났다 → tasks가 아니라 done_tasks
    assert len(body["tasks"]) == 4
    assert [t["title"] for t in body["done_tasks"]] == ["참고 사례 조사"]
    assert body["done_tasks"][0]["state"] == "done"
    assert body["done_tasks"][0]["source"]["topic"] == "역할 나누기"
    assert all(t["confirmed_by_name"] == "지수" for t in body["tasks"])
    # 할 일 목록과 같은 모양이라 프론트가 할 일 행 하나로 그린다
    task = next(t for t in body["tasks"] if t["title"] == "프로토타입 화면 구현")
    assert task["source"]["topic"] == "중간 발표 자료 나누기"
    assert task["can_change_status"] is True  # 현우가 담당
    assert task["can_edit"] is True
    assert "is_late" in task
    assert len(body["suggestions"]) == 3
    assert [a["name"] for a in body["attendees"]] == ["지수", "민지", "현우", "서연"]


def test_기록이_없는_회의는_빈_원문과_요약_없음으로_온다(
    client: TestClient, seeded: Session, login
) -> None:
    room = _room(seeded)
    meeting = _meeting(seeded, "역할 나누기")
    login("지수")

    body = client.get(_url(room, f"/{meeting.id}")).json()

    assert body["transcript"] == []
    assert body["minutes"] is None
    assert body["transcript_mode"] is None


def test_버린_제안은_회의록에서_빠진다(
    client: TestClient, seeded: Session, login
) -> None:
    room = _room(seeded)
    meeting = _meeting(seeded, "중간 발표 자료 나누기")
    dropped = seeded.exec(select(Task).where(Task.confirmed == False)).first()  # noqa: E712
    dropped.dropped = True
    seeded.add(dropped)
    seeded.commit()
    login("지수")

    body = client.get(_url(room, f"/{meeting.id}")).json()
    summary = client.get(_url(room)).json()["meetings"][0]

    assert len(body["suggestions"]) == 2
    assert summary["suggestion_count"] == 2


def test_다른_방의_회의는_404다(client: TestClient, seeded: Session, login) -> None:
    room = _room(seeded)
    other = Room(
        name="다른 방",
        start_date=date(2026, 11, 1),
        due_date=date(2026, 12, 1),
        eval_method="발표",
        member_count=2,
        invite_code="OTHER1",
        leader_user_id=room.leader_user_id,
    )
    seeded.add(other)
    seeded.flush()
    stranger = Meeting(
        room_id=other.id,
        topic="남의 회의",
        start_at=datetime(2026, 11, 2, 10, tzinfo=KST),
        end_at=datetime(2026, 11, 2, 11, tzinfo=KST),
        mode=Mode.ONLINE,
        status=MeetingStatus.DONE,
    )
    seeded.add(stranger)
    seeded.commit()
    login("지수")

    res = client.get(_url(room, f"/{stranger.id}"))

    assert res.status_code == 404


# ── 기록 시작 ───────────────────────────────────────────────────────


def test_잡힌_회의에_기록을_붙인다(client: TestClient, seeded: Session, login) -> None:
    room = _room(seeded)
    meeting = _meeting(seeded, "역할 나누기")
    login("서연")

    before = len(seeded.exec(select(Meeting)).all())

    res = client.post(_url(room), json={"meeting_id": meeting.id})

    # 새로 만든 게 아니라 있는 회의를 돌려주므로 201이 아니라 200
    assert res.status_code == 200, res.text
    assert res.json()["id"] == meeting.id
    assert len(seeded.exec(select(Meeting)).all()) == before


@pytest.mark.parametrize("status", [MeetingStatus.PROPOSED, MeetingStatus.CANCELLED])
def test_확정_전이나_취소된_회의에는_직접_쓸_수_없다(
    client: TestClient, seeded: Session, login, status: MeetingStatus
) -> None:
    room = _room(seeded)
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
    login("지수")

    res = client.put(_url(room, f"/{meeting.id}/transcript"), json={"text": "지수: 안녕"})

    assert res.status_code == 409
    assert res.json()["code"] == "NOT_CONFIRMED"
    seeded.refresh(meeting)
    assert meeting.transcript_mode is None


def test_회의안에는_기록을_붙일_수_없다(
    client: TestClient, seeded: Session, login
) -> None:
    room = _room(seeded)
    proposed = Meeting(
        room_id=room.id,
        topic="조율 중",
        start_at=datetime(2026, 11, 12, 14, tzinfo=KST),
        end_at=datetime(2026, 11, 12, 16, tzinfo=KST),
        mode=Mode.ONLINE,
        status=MeetingStatus.PROPOSED,
    )
    seeded.add(proposed)
    seeded.commit()
    login("지수")

    res = client.post(_url(room), json={"meeting_id": proposed.id})

    assert res.status_code == 409
    assert res.json()["code"] == "NOT_CONFIRMED"


def test_잡힌_회의_없이_바로_기록을_시작한다(
    client: TestClient, seeded: Session, login
) -> None:
    room = _room(seeded)
    demo_clock.set_clock(seeded, datetime(2026, 11, 10, 15, tzinfo=KST))
    seeded.commit()
    login("민지")

    res = client.post(_url(room), json={"topic": "급한 회의", "mode": "online"})

    assert res.status_code == 201, res.text
    body = res.json()
    assert body["topic"] == "급한 회의"
    assert body["status"] == "confirmed"
    assert body["start_at"].startswith("2026-11-10T15:00:00")
    assert body["start_at"].endswith("+09:00")
    topics = [m["topic"] for m in client.get(_url(room)).json()["meetings"]]
    assert "급한 회의" in topics


def test_주제_없이_새_회의를_시작하면_400이다(
    client: TestClient, seeded: Session, login
) -> None:
    login("지수")

    res = client.post(_url(_room(seeded)), json={})

    assert res.status_code == 400
    assert res.json()["field"] == "topic"


# ── 직접 쓰기 ───────────────────────────────────────────────────────


def test_직접_쓰면_줄과_말한_사람으로_나뉜다(
    client: TestClient, seeded: Session, login
) -> None:
    room = _room(seeded)
    meeting = _meeting(seeded, "역할 나누기")
    login("지수")
    text = "지수: 시작할게요\n\n참고: 다음 주 휴강\n없는사람: 누구지\n민지 : 네\n"

    body = client.put(_url(room, f"/{meeting.id}/transcript"), json={"text": text}).json()

    assert [(line["speaker_name"], line["text"]) for line in body["transcript"]] == [
        ("지수", "시작할게요"),
        (None, "참고: 다음 주 휴강"),
        (None, "없는사람: 누구지"),
        ("민지", "네"),
    ]
    assert body["transcript_mode"] == "manual"


def test_다시_쓰면_원문이_통째로_바뀐다(
    client: TestClient, seeded: Session, login
) -> None:
    room = _room(seeded)
    meeting = _meeting(seeded, "중간 발표 자료 나누기")  # 시드 원문 6줄
    login("지수")

    body = client.put(
        _url(room, f"/{meeting.id}/transcript"), json={"text": "서연: 한 줄만 남김"}
    ).json()

    assert [(line["seq"], line["text"]) for line in body["transcript"]] == [
        (0, "한 줄만 남김")
    ]


@pytest.mark.parametrize("text", ["", "  \n\n  ", "지수:\n민지 :  "])
def test_남는_줄이_없는_글은_거절하고_원문을_지우지_않는다(
    client: TestClient, seeded: Session, login, text: str
) -> None:
    # 실수로 빈 칸을 저장하면 받아적은 원문까지 통째로 사라지고 되돌릴 수 없다
    room = _room(seeded)
    meeting = _meeting(seeded, "중간 발표 자료 나누기")  # 시드 원문 6줄
    login("지수")

    res = client.put(_url(room, f"/{meeting.id}/transcript"), json={"text": text})

    assert res.status_code == 400, res.text
    error = res.json()
    assert (error["code"], error["field"]) == ("INVALID_INPUT", "text")
    assert error["message"] == "회의 내용을 적어 주세요."
    after = client.get(_url(room, f"/{meeting.id}")).json()
    assert len(after["transcript"]) == 6


def test_전각_콜론도_말한_사람으로_읽는다() -> None:
    lines = parse("현우：확인했어요", {"현우": 3})

    assert lines[0].speaker_user_id == 3
    assert lines[0].text == "확인했어요"
