"""왜 이 시간인가(meeting/why.py). 고른 시간과 2순위를 같은 기준으로 비교한다."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.meeting.models import CandidateSlot, Meeting, MeetingResponse, Scheduling, SlotCost, YieldEntry
from app.meeting.why import explain
from app.shared.base import KST
from app.shared.enums import MeetingStatus, Mode, ResponseState, SchedulingPhase, SchedulingStatus
from app.shared.models import Membership, Room, User

API = "/api/v1"
TUE = datetime(2026, 11, 17, tzinfo=KST)
NAMES = ["지수", "민지", "현우", "서연"]


@pytest.fixture
def 팀(session: Session) -> tuple[Room, dict[str, int]]:
    users = [User(name=n) for n in NAMES]
    session.add_all(users)
    session.flush()
    room = Room(
        name="팀플", start_date=date(2026, 9, 1), due_date=date(2026, 12, 20), eval_method="발표",
        member_count=4, invite_code="WHY123", leader_user_id=users[0].id,  # type: ignore[arg-type]
    )
    session.add(room)
    session.flush()
    session.add_all([Membership(room_id=room.id, user_id=u.id) for u in users])  # type: ignore[arg-type]
    session.commit()
    return room, {u.name: u.id for u in users}  # type: ignore[misc]


def _현우가_전에_많이_참음(session: Session, room: Room, ids: dict[str, int]) -> None:
    past = Meeting(room_id=room.id, topic="지난 회의", start_at=TUE - timedelta(days=7),  # type: ignore[arg-type]
                   end_at=TUE - timedelta(days=7, hours=-1), mode=Mode.ONLINE, status=MeetingStatus.DONE)
    session.add(past)
    session.flush()
    for uid in ids.values():
        session.add(MeetingResponse(meeting_id=past.id, user_id=uid, state=ResponseState.ACCEPTED,  # type: ignore[arg-type]
                                    responded_at=past.start_at))
    session.add(YieldEntry(room_id=room.id, meeting_id=past.id, user_id=ids["현우"], points=2,  # type: ignore[arg-type]
                           discomfort=4, reason=""))
    session.commit()


def _조율(session: Session, room: Room, ids: dict[str, int], 후보: list[tuple[int, dict[str, int]]],
         chosen: int = 0) -> Meeting:
    """후보: [(화요일 몇 시, {이름: 점수}), …]. chosen번째 후보로 회의가 났다."""
    s = Scheduling(room_id=room.id, started_by=ids["지수"], topic="중간 발표", window_start=TUE,  # type: ignore[arg-type]
                   window_end=TUE + timedelta(days=1), duration_min=90, mode=Mode.ANY,
                   status=SchedulingStatus.AGREED, rounds_used=1)
    session.add(s)
    session.flush()
    slots = []
    for hour, scores in 후보:
        slot = CandidateSlot(scheduling_id=s.id, start_at=TUE + timedelta(hours=hour),  # type: ignore[arg-type]
                             end_at=TUE + timedelta(hours=hour, minutes=90), total_cost=0,
                             phase=SchedulingPhase.ALL, round_no=1)
        session.add(slot)
        session.flush()
        for name, uid in ids.items():
            score = scores.get(name, 1)
            session.add(SlotCost(candidate_slot_id=slot.id, user_id=uid, score=score, available=score < 5,  # type: ignore[arg-type]
                                 reason="수업 바로 뒤라 이동이 빠듯합니다" if score > 1 else "비어 있는 시간입니다"))
        slots.append(slot)
    pick = slots[chosen]
    meeting = Meeting(room_id=room.id, scheduling_id=s.id, candidate_slot_id=pick.id, topic="중간 발표",  # type: ignore[arg-type]
                      start_at=pick.start_at, end_at=pick.end_at, mode=Mode.ONLINE, status=MeetingStatus.PROPOSED)
    session.add(meeting)
    session.commit()
    return meeting


def test_그동안_많이_맞춰_준_사람을_챙겨서_골랐다(session: Session, 팀) -> None:
    room, ids = 팀
    _현우가_전에_많이_참음(session, room, ids)
    # 15시: 민지 조금·현우 괜찮음 / 13시: 민지 괜찮음·현우 조금 — 합은 같다
    m = _조율(session, room, ids, [(15, {"민지": 2}), (13, {"현우": 2})], chosen=0)

    why = explain(session, m)

    assert why is not None
    assert why.rule == "yield_first"
    assert "현우님" in why.summary and "민지님은 조금 불편해요" in why.summary
    현우 = next(p for p in why.people if p.name == "현우")
    assert (현우.here, 현우.there) == ("ok", "some")


def test_2순위에_많이_불편한_사람이_있으면_그_이유(session: Session, 팀) -> None:
    room, ids = 팀
    m = _조율(session, room, ids, [(15, {"민지": 2}), (13, {"서연": 4})], chosen=0)
    why = explain(session, m)
    assert why is not None and why.rule == "fewer_reject"
    assert "서연님이 많이 불편한 시간" in why.summary


def test_다_같으면_이른_시간(session: Session, 팀) -> None:
    room, ids = 팀
    m = _조율(session, room, ids, [(13, {}), (15, {})], chosen=0)
    why = explain(session, m)
    assert why is not None and why.rule == "earlier"


def test_기준상_나은_시간을_안_골랐으면_앞에서_거절된_것(session: Session, 팀) -> None:
    room, ids = 팀
    m = _조율(session, room, ids, [(13, {}), (15, {"민지": 3})], chosen=1)
    why = explain(session, m)
    assert why is not None and why.rule == "rejected_before"


def test_조율_없이_만든_회의는_없다(session: Session, 팀) -> None:
    room, _ = 팀
    m = Meeting(room_id=room.id, topic="바로 기록", start_at=TUE, end_at=TUE + timedelta(hours=1),  # type: ignore[arg-type]
                mode=Mode.ONLINE, status=MeetingStatus.CONFIRMED)
    session.add(m)
    session.commit()
    assert explain(session, m) is None


def test_회의_화면_응답에_남의_숫자가_없다(client: TestClient, session: Session, 팀, login) -> None:
    room, ids = 팀
    m = _조율(session, room, ids, [(15, {"민지": 2}), (13, {"서연": 4})], chosen=0)
    login("지수")
    body = client.get(f"{API}/rooms/{room.id}/proposals/{m.id}").json()
    assert body["why"]["rule"] == "fewer_reject"
    for person in body["why"]["people"]:
        assert set(person) == {"name", "here", "there", "reason_here"}
        assert person["here"] in ("ok", "some", "much", None)
