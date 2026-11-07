"""주간 시간표 (GET /rooms/{room_id}/me/schedule).

수업·일정·팀 회의가 한 주 안에 제자리에 펼쳐지는지, 그리고 **남의 일정이 절대
안 나가는지**를 본다. 펼치는 규칙은 조율과 같은 expand_busy라, 여기서 어긋나면
조율이 막힌 시간으로 보는 것과 화면이 다르다는 뜻이다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.me.models import ScheduleItem
from app.meeting.models import Meeting, MeetingResponse
from app.shared.base import KST
from app.shared.enums import (
    MeetingStatus,
    Mode,
    Recurrence,
    ResponseState,
    ScheduleKind,
    ScheduleSource,
)
from app.shared.models import Membership, Room, User

API = "/api/v1"
MON = date(2026, 11, 9)  # 월요일


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=KST)


@pytest.fixture
def 방(session: Session) -> tuple[Room, User, User]:
    지수, 민지 = User(name="지수"), User(name="민지")
    session.add_all([지수, 민지])
    session.flush()
    room = Room(
        name="서비스디자인 팀 프로젝트",
        start_date=date(2026, 10, 20),
        due_date=date(2026, 12, 11),
        eval_method="최종 발표 + 시연",
        member_count=2,
        invite_code="T9K2QM",
        leader_user_id=지수.id,  # type: ignore[arg-type]
    )
    session.add(room)
    session.flush()
    session.add_all(
        [
            Membership(room_id=room.id, user_id=지수.id),  # type: ignore[arg-type]
            Membership(room_id=room.id, user_id=민지.id),  # type: ignore[arg-type]
        ]
    )
    session.commit()
    return room, 지수, 민지


def _매주(user: User, *, weekday: int, start: int, end: int, title: str,
         kind: ScheduleKind = ScheduleKind.CLASS,
         valid_from: date | None = None, valid_to: date | None = None) -> ScheduleItem:
    return ScheduleItem(
        user_id=user.id,  # type: ignore[arg-type]
        source=ScheduleSource.EVERYTIME if kind == ScheduleKind.CLASS else ScheduleSource.MANUAL,
        kind=kind,
        title=title,
        recurrence=Recurrence.WEEKLY,
        weekday=weekday,
        start_min=start,
        end_min=end,
        valid_from=valid_from,
        valid_to=valid_to,
    )


def _보기(client: TestClient, room: Room, **params) -> dict:
    res = client.get(f"{API}/rooms/{room.id}/me/schedule", params=params)
    assert res.status_code == 200, res.text
    return res.json()


def test_매주_수업이_그_주_요일에_펼쳐진다(client: TestClient, session: Session, 방, login) -> None:
    room, 지수, _ = 방
    session.add(_매주(지수, weekday=2, start=9 * 60, end=10 * 60 + 30, title="서비스디자인"))
    session.commit()
    login("지수")

    body = _보기(client, room, week="2026-11-11")  # 수요일을 줘도 그 주 월~일

    assert (body["week_start"], body["week_end"]) == ("2026-11-09", "2026-11-15")
    [수업] = body["items"]
    assert 수업["kind"] == "class"
    assert 수업["title"] == "서비스디자인"
    assert 수업["source"] == "everytime"
    assert datetime.fromisoformat(수업["start_at"]) == at(date(2026, 11, 11), 9)
    assert datetime.fromisoformat(수업["end_at"]) == at(date(2026, 11, 11), 10, 30)


def test_학기_밖의_수업은_안_나온다(client: TestClient, session: Session, 방, login) -> None:
    room, 지수, _ = 방
    session.add(_매주(지수, weekday=0, start=540, end=600, title="지난 학기 수업",
                    valid_to=date(2026, 10, 31)))
    session.commit()
    login("지수")

    assert _보기(client, room, week=str(MON))["items"] == []


def test_알바와_약속은_일정으로_묶이고_제목_없는_약속은_null이다(
    client: TestClient, session: Session, 방, login
) -> None:
    room, 지수, _ = 방
    session.add_all(
        [
            _매주(지수, weekday=4, start=18 * 60, end=21 * 60, title="편의점 알바",
                 kind=ScheduleKind.PARTTIME),
            ScheduleItem(
                user_id=지수.id,  # type: ignore[arg-type]
                source=ScheduleSource.GOOGLE,
                kind=ScheduleKind.APPOINTMENT,
                title=None,
                recurrence=Recurrence.ONCE,
                start_at=at(date(2026, 11, 10), 15),
                end_at=at(date(2026, 11, 10), 16),
            ),
        ]
    )
    session.commit()
    login("지수")

    items = _보기(client, room, week=str(MON))["items"]

    assert [i["kind"] for i in items] == ["event", "event"]
    assert items[0]["title"] is None and items[0]["source"] == "google"  # 화 15시가 먼저
    assert items[1]["title"] == "편의점 알바"


def test_남의_일정은_안_나온다(client: TestClient, session: Session, 방, login) -> None:
    room, _, 민지 = 방
    session.add(_매주(민지, weekday=0, start=540, end=600, title="민지 수업"))
    session.commit()
    login("지수")

    assert _보기(client, room, week=str(MON))["items"] == []


def test_팀_회의가_같이_나오고_거절한_회의는_빠진다(
    client: TestClient, session: Session, 방, login
) -> None:
    room, 지수, 민지 = 방
    간다 = Meeting(room_id=room.id, topic="발표 리허설", start_at=at(MON, 14),  # type: ignore[arg-type]
                 end_at=at(MON, 16), mode=Mode.OFFLINE, status=MeetingStatus.CONFIRMED)
    거절 = Meeting(room_id=room.id, topic="안 가는 회의", start_at=at(MON, 18),  # type: ignore[arg-type]
                 end_at=at(MON, 19), mode=Mode.OFFLINE, status=MeetingStatus.PROPOSED)
    session.add_all([간다, 거절])
    session.flush()
    session.add_all(
        [
            MeetingResponse(meeting_id=간다.id, user_id=지수.id, state=ResponseState.ACCEPTED, responded_at=at(MON, 9)),  # type: ignore[arg-type]
            MeetingResponse(meeting_id=거절.id, user_id=지수.id, state=ResponseState.DECLINED, responded_at=at(MON, 9)),  # type: ignore[arg-type]
        ]
    )
    session.commit()
    login("지수")

    [회의] = _보기(client, room, week=str(MON))["items"]

    assert 회의["kind"] == "meeting"
    assert 회의["title"] == "발표 리허설"
    assert 회의["meeting_id"] == 간다.id
    assert 회의["meeting_status"] == "confirmed"
    assert 회의["source"] is None


def test_다른_주를_고르면_그_주가_나온다(client: TestClient, session: Session, 방, login) -> None:
    room, 지수, _ = 방
    session.add(_매주(지수, weekday=0, start=540, end=600, title="월요 수업"))
    session.commit()
    login("지수")

    다음주 = _보기(client, room, week="2026-11-16")

    assert 다음주["week_start"] == "2026-11-16"
    assert datetime.fromisoformat(다음주["items"][0]["start_at"]).date() == date(2026, 11, 16)


def test_주를_안_주면_시연_시계의_이번_주다(client: TestClient, session: Session, 방, login) -> None:
    from app.shared import demo_clock

    room, _, _ = 방
    demo_clock.set_clock(session, at(date(2026, 11, 19), 10))  # 목요일
    session.commit()
    login("지수")

    assert _보기(client, room)["week_start"] == "2026-11-16"


def test_팀원이_아니면_못_본다(client: TestClient, session: Session, 방, login) -> None:
    room, _, _ = 방
    session.add(User(name="남"))
    session.commit()
    login("남")

    assert client.get(f"{API}/rooms/{room.id}/me/schedule").status_code == 403
