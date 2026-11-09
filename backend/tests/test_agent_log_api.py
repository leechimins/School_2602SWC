"""에이전트가 한 일 · 양보 기록 (GET /rooms/{room_id}/agent-log).

지켜야 하는 것이 둘이다.

**일이 생기면 한 줄씩 남는다.** 합의(제안), 조정(바로 확정), 전원 수락(확정),
거절(다시 조율). 전에는 agent_log 테이블이 있었지만 아무도 안 써서 화면이
늘 비어 있었다(프론트는 목을 썼다).

**방 전체가 보는 화면이라 점수 숫자가 없다.** yield_entry.reason에는
"내 불편 3/5만큼 맞춰 줘서 +1"처럼 숫자가 들어 있어 그대로 내보내면 안 된다.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.meeting.agent_loop import run_rounds
from app.meeting.models import CandidateSlot, Meeting, Scheduling, SlotCost
from app.shared.base import KST
from app.shared.enums import MeetingStatus, Mode, SchedulingPhase, SchedulingStatus
from app.shared.models import Membership, Room, User

API = "/api/v1"
MON = datetime(2026, 11, 9, 9, 0, tzinfo=KST)


class 팀:
    def __init__(self, room: Room, 지수: User, 현우: User, 민지: User) -> None:
        self.room, self.지수, self.현우, self.민지 = room, 지수, 현우, 민지

    @property
    def id(self) -> int:
        assert self.room.id is not None
        return self.room.id


@pytest.fixture
def 방(session: Session) -> 팀:
    지수, 현우, 민지 = User(name="지수"), User(name="현우"), User(name="민지")
    session.add_all([지수, 현우, 민지])
    session.flush()
    room = Room(
        name="서비스디자인 팀 프로젝트",
        start_date=date(2026, 10, 20),
        due_date=date(2026, 12, 11),
        eval_method="최종 발표 + 시연",
        member_count=3,
        invite_code="T9K2QM",
        leader_user_id=지수.id,  # type: ignore[arg-type]
    )
    session.add(room)
    session.flush()
    for u in (지수, 현우, 민지):
        session.add(Membership(room_id=room.id, user_id=u.id))  # type: ignore[arg-type]
    session.commit()
    return 팀(room, 지수, 현우, 민지)


def _조율(session: Session, 방: 팀) -> Scheduling:
    s = Scheduling(
        room_id=방.id,
        started_by=방.지수.id,  # type: ignore[arg-type]
        topic="발표 리허설",
        window_start=MON,
        window_end=MON + timedelta(days=4),
        duration_min=120,
        mode=Mode.OFFLINE,
        status=SchedulingStatus.RUNNING,
    )
    session.add(s)
    session.flush()
    return s


def _후보(session: Session, s: Scheduling, *, hour: int, 점수: dict[int, int]) -> None:
    slot = CandidateSlot(
        scheduling_id=s.id,  # type: ignore[arg-type]
        start_at=MON.replace(hour=hour),
        end_at=MON.replace(hour=hour + 2),
        total_cost=float(sum(점수.values())),
        phase=SchedulingPhase.ALL,
        round_no=1,
    )
    session.add(slot)
    session.flush()
    for user_id, score in 점수.items():
        session.add(
            SlotCost(
                candidate_slot_id=slot.id,  # type: ignore[arg-type]
                user_id=user_id,
                score=score,
                available=True,
                reason="알바와 겹칩니다" if score >= 4 else "비어 있는 시간입니다",
            )
        )
    session.commit()


def _합의(session: Session, 방: 팀, *, 대안: bool = False) -> Meeting:
    """14시로 합의된 회의. 지수 1·현우 2·민지 3이라 확정되면 현우·민지가 양보 점수를 받는다."""
    s = _조율(session, 방)
    _후보(session, s, hour=14, 점수={방.지수.id: 1, 방.현우.id: 2, 방.민지.id: 3})  # type: ignore[dict-item]
    if 대안:
        _후보(session, s, hour=16, 점수={방.지수.id: 2, 방.현우.id: 2, 방.민지.id: 2})  # type: ignore[dict-item]
    list(run_rounds(session, s))
    return session.exec(select(Meeting).where(Meeting.status == MeetingStatus.PROPOSED)).one()


def _기록(client: TestClient, 방: 팀) -> dict:
    res = client.get(f"{API}/rooms/{방.id}/agent-log")
    assert res.status_code == 200, res.text
    return res.json()


def _수락(client: TestClient, login, 방: 팀, meeting_id: int, *이름: str) -> None:
    for n in 이름:
        login(n)
        res = client.post(
            f"{API}/rooms/{방.id}/proposals/{meeting_id}/respond", json={"accept": True}
        )
        assert res.status_code == 200, res.text


# ── 에이전트가 한 일 ─────────────────────────────────────────────────


def test_합의하면_제안했다는_줄이_남는다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    meeting = _합의(session, 방)
    login("지수")

    log = _기록(client, 방)["agent_log"]

    assert len(log) == 1
    assert log[0]["what"] == "발표 리허설 제안 · 11월 9일(월) 14:00–16:00"
    assert log[0]["why"] == meeting.rationale  # 판단 에이전트가 모두에게 한 말 그대로


def test_전원이_수락하면_확정됐다는_줄이_위에_쌓인다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    meeting = _합의(session, 방)
    _수락(client, login, 방, meeting.id, "지수", "현우", "민지")  # type: ignore[arg-type]

    log = _기록(client, 방)["agent_log"]

    assert [l["what"] for l in log] == [
        "발표 리허설 확정",  # 최신이 위
        "발표 리허설 제안 · 11월 9일(월) 14:00–16:00",
    ]
    assert log[0]["why"] == "모두 수락했어요"


def test_조정되면_정했다는_줄과_이유가_남는다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """민지 5점이라 거절 → 다른 후보가 없어 판단 에이전트가 정하고 바로 확정."""
    s = _조율(session, 방)
    _후보(session, s, hour=14, 점수={방.지수.id: 1, 방.현우.id: 2, 방.민지.id: 5})  # type: ignore[dict-item]
    list(run_rounds(session, s))
    login("지수")

    log = _기록(client, 방)["agent_log"]

    assert log[0]["what"] == "발표 리허설 확정 · 11월 9일(월) 14:00–16:00"
    assert "판단 에이전트가 정했어요" in log[0]["why"]


def test_거절하면_다시_조율한다는_줄이_남는다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    meeting = _합의(session, 방, 대안=True)
    login("현우")
    client.post(
        f"{API}/rooms/{방.id}/proposals/{meeting.id}/respond", json={"accept": False}
    )

    whats = [l["what"] for l in _기록(client, 방)["agent_log"]]
    다시 = next(l for l in _기록(client, 방)["agent_log"] if l["what"] == "발표 리허설 다시 조율")

    assert 다시["why"] == "현우 님이 그 시간은 어렵다고 했어요"
    # 다시 돈 조율이 대안 16시로 새로 제안한 줄도 남는다
    assert "발표 리허설 제안 · 11월 9일(월) 16:00–18:00" in whats


# ── 양보 기록 ────────────────────────────────────────────────────────


def test_확정되면_누가_맞춰_줬는지가_이름과_회의_날짜로_나온다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    meeting = _합의(session, 방)
    _수락(client, login, 방, meeting.id, "지수", "현우", "민지")  # type: ignore[arg-type]

    records = _기록(client, 방)["yield_records"]

    assert {r["name"] for r in records} == {"현우", "민지"}  # 지수는 1점(괜찮음)이라 없다
    assert all(r["meeting_label"] == "11월 9일 회의" for r in records)
    assert all(r["why"] == "조금 불편한 시간을 맞춰 줬어요" for r in records)


def test_점수_숫자가_응답_어디에도_없다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """명세 권장 규칙 3. yield_entry.reason에는 "3/5", "+1"이 들어 있다."""
    meeting = _합의(session, 방)
    _수락(client, login, 방, meeting.id, "지수", "현우", "민지")  # type: ignore[arg-type]

    body = _기록(client, 방)
    # 글자 칸만 본다. 시각(at)의 "+09:00"은 숫자가 맞다
    글 = " ".join(
        [l["what"] + l["why"] for l in body["agent_log"]]
        + [r["why"] + r["meeting_label"] for r in body["yield_records"]]
    )

    assert not re.search(r"\d/5", 글)
    assert not re.search(r"\+\d", 글)


def test_팀원이_아니면_못_본다(client: TestClient, session: Session, 방: 팀, login) -> None:
    session.add(User(name="남"))
    session.commit()
    login("남")

    assert client.get(f"{API}/rooms/{방.id}/agent-log").status_code == 403
