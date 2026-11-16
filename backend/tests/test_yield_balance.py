"""양보 잔고 — 참으면 쌓이고 배려를 받으면 쓴다(agent_loop.yield_balances).

회의마다 참석자 각자: 잔고 += 받은 양보 점수 − 참석자 평균 양보 점수.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlmodel import Session

from app.meeting.agent_loop import yield_balances
from app.meeting.models import Meeting, MeetingResponse, YieldEntry
from app.meeting.prompts import yield_step
from app.meeting.scorer import Cost, yield_weighted_cost
from app.shared.base import KST
from app.shared.enums import MeetingStatus, Mode, ResponseState
from app.shared.models import Membership, Room, User

NAMES = ["지수", "민지", "현우", "서연"]


@pytest.fixture
def 팀(session: Session) -> tuple[Room, dict[str, int]]:
    users = [User(name=n) for n in NAMES]
    session.add_all(users)
    session.flush()
    room = Room(
        name="팀플", start_date=date(2026, 9, 1), due_date=date(2026, 12, 20), eval_method="발표",
        member_count=4, invite_code="BAL123", leader_user_id=users[0].id,  # type: ignore[arg-type]
    )
    session.add(room)
    session.flush()
    session.add_all([Membership(room_id=room.id, user_id=u.id) for u in users])  # type: ignore[arg-type]
    session.commit()
    return room, {u.name: u.id for u in users}  # type: ignore[misc]


_n = 0


def _회의(
    session: Session,
    room: Room,
    ids: dict[str, int],
    points: dict[str, int],
    *,
    declined: tuple[str, ...] = (),
    status: MeetingStatus = MeetingStatus.CONFIRMED,
) -> None:
    """참석자 전원 + 받은 양보 점수(0이면 행 없음)로 회의 하나를 만든다."""
    global _n
    _n += 1
    start = datetime(2026, 10, 1, 10, tzinfo=KST) + timedelta(days=_n)
    meeting = Meeting(
        room_id=room.id, topic=f"회의 {_n}", start_at=start, end_at=start + timedelta(hours=1),  # type: ignore[arg-type]
        mode=Mode.ONLINE, status=status, rationale="",
    )
    session.add(meeting)
    session.flush()
    for name, uid in ids.items():
        state = ResponseState.DECLINED if name in declined else ResponseState.ACCEPTED
        session.add(MeetingResponse(meeting_id=meeting.id, user_id=uid, state=state, responded_at=start))  # type: ignore[arg-type]
        p = points.get(name, 0)
        if p and name not in declined:
            session.add(
                YieldEntry(room_id=room.id, meeting_id=meeting.id, user_id=uid, points=p,  # type: ignore[arg-type]
                           discomfort=2 if p == 1 else 4, reason="")
            )
    session.commit()


def _잔고(session: Session, room: Room, ids: dict[str, int]) -> dict[str, float]:
    got = yield_balances(session, room.id)  # type: ignore[arg-type]
    return {name: round(got[uid], 4) for name, uid in ids.items()}


def test_더_참은_사람은_쌓이고_배려받은_사람은_준다(session: Session, 팀) -> None:
    room, ids = 팀
    # 1번: 현우가 많이 참았다(+2). 평균 0.5
    _회의(session, room, ids, {"현우": 2})
    assert _잔고(session, room, ids) == {"지수": -0.5, "민지": -0.5, "현우": 1.5, "서연": -0.5}

    # 2번: 현우를 챙겨 현우는 괜찮음, 민지가 조금 참았다(+1). 평균 0.25
    _회의(session, room, ids, {"민지": 1})
    assert _잔고(session, room, ids) == {"지수": -0.75, "민지": 0.25, "현우": 1.25, "서연": -0.75}


def test_거절한_사람과_확정_안_된_회의는_안_센다(session: Session, 팀) -> None:
    room, ids = 팀
    # 서연이 거절했다 → 참석자 셋만으로 평균(2/3)
    _회의(session, room, ids, {"현우": 2}, declined=("서연",))
    # 아직 확정 전인 회의는 잔고에 안 들어간다
    _회의(session, room, ids, {"민지": 2}, status=MeetingStatus.PROPOSED)

    got = _잔고(session, room, ids)
    assert got["서연"] == 0
    assert got["현우"] == round(2 - 2 / 3, 4)
    assert got["민지"] == round(-2 / 3, 4)


def test_회의를_스무_번_해도_합은_0이고_차이가_남는다(session: Session, 팀) -> None:
    """누적 방식은 이쯤이면 전원 상한에 닿아 차이가 사라졌다."""
    room, ids = 팀
    for i in range(20):
        _회의(session, room, ids, {"현우": 2} if i % 2 == 0 else {"민지": 1})
    got = _잔고(session, room, ids)
    assert abs(sum(got.values())) < 1e-6
    assert got["현우"] > got["민지"] > got["지수"]


def test_잔고가_높은_사람의_불편을_무겁게_센다() -> None:
    """비슷한 두 시간이면 그동안 더 참은 현우가 편한 쪽을 고른다."""
    a = [Cost(1, 2, True, ""), Cost(3, 1, True, "")]  # 민지(1) 조금, 현우(3) 괜찮음
    b = [Cost(1, 1, True, ""), Cost(3, 2, True, "")]  # 민지 괜찮음, 현우 조금
    잔고 = {1: -0.5, 3: 1.5}
    assert yield_weighted_cost(a, 잔고) < yield_weighted_cost(b, 잔고)
    # 배려를 받아 온 사람(음수)은 1배 — 깎이지 않는다
    assert yield_weighted_cost([Cost(1, 3, True, "")], {1: -2.0}) == 3


def test_잔고는_단계_말로만_나간다() -> None:
    assert [yield_step(x) for x in (-1, 0, 0.5, 1.5, 3)] == [
        "아직 없음", "아직 없음", "조금 맞춰 줌", "많이 맞춰 줌", "많이 맞춰 줌"
    ]
