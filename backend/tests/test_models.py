"""문서에 적은 제약이 실제로 물리는지 본다.

db-설계.md에 "CHECK를 건다"고 써 놓고 코드에서 빠뜨리는 것이 제일 흔한
사고다. 그러면 문서를 읽은 사람은 DB가 막아 준다고 믿고 검사를 생략한다.
그래서 이 테스트는 성공이 아니라 거부를 확인한다.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlmodel import Session, SQLModel, select

from app.demo.models import DemoState
from app.me.models import Preference
from app.meeting.models import (
    CandidateSlot,
    Meeting,
    MeetingResponse,
    Scheduling,
    SlotCost,
    Utterance,
    YieldEntry,
)
from app.shared import demo_clock
from app.shared.base import KST
from app.shared.enums import (
    Daypart,
    MeetingStatus,
    Mode,
    ResponseState,
    SchedulingStatus,
    SpeakerKind,
)
from app.shared.models import Membership, Room, User

REJECTED = (IntegrityError, DBAPIError)


def at(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=KST)


def a_room(session: Session) -> tuple[User, Room]:
    user = User(name="지수")
    session.add(user)
    session.flush()
    room = Room(
        name="서비스디자인 팀 프로젝트",
        start_date=date(2026, 10, 20),
        due_date=date(2026, 12, 11),
        eval_method="발표",
        member_count=4,
        invite_code="ABC123",
        leader_user_id=user.id,
    )
    session.add(room)
    session.flush()
    return user, room


def a_scheduling(session: Session, room: Room, user: User, **kw) -> Scheduling:
    """조율 한 행. 넘긴 값이 기본값을 덮는다.

    flush까지 하므로, 제약 위반을 일으키는 호출은 pytest.raises 블록 안에서
    불러야 한다 — 예외가 이 안에서 나기 때문이다.
    """
    kw.setdefault("topic", "발표 자료 나누기")
    kw.setdefault("window_start", at(2026, 11, 10, 0))
    kw.setdefault("window_end", at(2026, 11, 14, 23))
    kw.setdefault("duration_min", 120)
    kw.setdefault("mode", Mode.ANY)
    kw.setdefault("status", SchedulingStatus.RUNNING)
    row = Scheduling(room_id=room.id, started_by=user.id, **kw)
    session.add(row)
    session.flush()
    return row


def a_meeting(session: Session, room: Room, **kw) -> Meeting:
    kw.setdefault("topic", "발표 자료 나누기")
    kw.setdefault("start_at", at(2026, 11, 12, 16))
    kw.setdefault("end_at", at(2026, 11, 12, 18))
    kw.setdefault("mode", Mode.OFFLINE)
    kw.setdefault("status", MeetingStatus.PROPOSED)
    row = Meeting(room_id=room.id, **kw)
    session.add(row)
    session.flush()
    return row


def test_테이블_17개가_생긴다(session: Session) -> None:
    names = set(SQLModel.metadata.tables)
    assert len(names) == 17, sorted(names)
    assert "scheduling_note" not in names, "11/3에 뺀 테이블이 살아 있다"
    # 레인이 갈리는 접점 세 곳이 다 있어야 A가 돌아간다.
    assert {"user", "room", "membership", "meeting", "demo_state"} <= names


def test_불편_점수는_1에서_5를_벗어나면_거부된다(session: Session) -> None:
    user, room = a_room(session)
    scheduling = a_scheduling(session, room, user)
    slot = CandidateSlot(
        scheduling_id=scheduling.id,
        start_at=at(2026, 11, 12, 16),
        end_at=at(2026, 11, 12, 18),
        total_cost=4.0,
        round_no=1,
    )
    session.add(slot)
    session.flush()

    session.add(
        SlotCost(candidate_slot_id=slot.id, user_id=user.id, score=6, reason="범위 밖")
    )
    with pytest.raises(REJECTED):
        session.flush()


def test_한_방에_도는_조율은_하나뿐이다(session: Session) -> None:
    """부분 인덱스. 조율 중에 팀장이 한 번 더 누르면 발언이 두 줄기로 섞인다."""
    user, room = a_room(session)
    a_scheduling(session, room, user)

    with pytest.raises(REJECTED):
        a_scheduling(session, room, user)


def test_끝난_조율은_같은_방에_여러_개여도_된다(session: Session) -> None:
    """부분 인덱스가 running만 막는지 확인한다. 전체 unique면 이게 깨진다."""
    user, room = a_room(session)
    a_scheduling(session, room, user, status=SchedulingStatus.AGREED)
    a_scheduling(session, room, user, status=SchedulingStatus.AGREED)
    session.flush()

    rows = session.exec(select(Scheduling).where(Scheduling.room_id == room.id)).all()
    assert len(rows) == 2


def test_같은_사람이_한_회의에_두_번_답할_수_없다(session: Session) -> None:
    user, room = a_room(session)
    meeting = a_meeting(session, room)

    session.add_all(
        [
            MeetingResponse(
                meeting_id=meeting.id, user_id=user.id, state=ResponseState.PENDING
            ),
            MeetingResponse(
                meeting_id=meeting.id, user_id=user.id, state=ResponseState.PENDING
            ),
        ]
    )
    with pytest.raises(REJECTED):
        session.flush()


def test_양보_점수는_1이나_2만_된다(session: Session) -> None:
    """차등이 +1/+2뿐이다. 3이 들어가면 누적 단계가 틀어진다."""
    user, room = a_room(session)
    meeting = a_meeting(session, room)

    session.add(
        YieldEntry(
            room_id=room.id,
            meeting_id=meeting.id,
            user_id=user.id,
            points=3,
            discomfort=5,
            reason="범위 밖",
        )
    )
    with pytest.raises(REJECTED):
        session.flush()


def test_확정된_회의에_any_방식은_들어갈_수_없다(session: Session) -> None:
    """조율 조건에는 '상관없음'이 있지만 잡힌 회의는 둘 중 하나여야 한다."""
    _, room = a_room(session)
    with pytest.raises(REJECTED):
        a_meeting(session, room, mode=Mode.ANY)


def test_판단_에이전트_발언에는_사람이_붙지_않는다(session: Session) -> None:
    user, room = a_room(session)
    scheduling = a_scheduling(session, room, user)

    session.add(
        Utterance(
            scheduling_id=scheduling.id,
            round_no=1,
            seq=1,
            speaker_kind=SpeakerKind.JUDGE,
            speaker_user_id=user.id,  # 붙으면 안 된다
            text="목요일 13:00을 제안합니다.",
        )
    )
    with pytest.raises(REJECTED):
        session.flush()


def test_시간표는_주간_반복과_한_번_중_하나로만_채워진다(session: Session) -> None:
    """weekly인데 요일이 없는 반쪽짜리 행을 막는다."""
    from app.me.models import ScheduleItem
    from app.shared.enums import Recurrence, ScheduleKind, ScheduleSource

    user, _ = a_room(session)
    session.add(
        ScheduleItem(
            user_id=user.id,
            source=ScheduleSource.MANUAL,
            kind=ScheduleKind.CLASS,
            recurrence=Recurrence.WEEKLY,
            weekday=None,  # weekly면 있어야 한다
            start_min=540,
            end_min=600,
        )
    )
    with pytest.raises(REJECTED):
        session.flush()


def test_선호_시간대는_배열로_오간다(session: Session) -> None:
    """Postgres text[]. 콤마 문자열을 파싱하지 않는다."""
    user, _ = a_room(session)
    session.add(
        Preference(
            user_id=user.id,
            day_start_min=600,
            day_end_min=1260,
            mode_pref=Mode.OFFLINE,
            dayparts=[Daypart.AFTERNOON, Daypart.EVENING],
        )
    )
    session.commit()

    saved = session.exec(select(Preference).where(Preference.user_id == user.id)).one()
    assert saved.dayparts == ["afternoon", "evening"]


def test_선호는_한_사람에_하나뿐이다(session: Session) -> None:
    user, _ = a_room(session)
    session.add_all([Preference(user_id=user.id), Preference(user_id=user.id)])
    with pytest.raises(REJECTED):
        session.flush()


def test_선호를_다_비워도_저장된다(session: Session) -> None:
    """브리프: 필수 항목은 없습니다. 네 개를 다 비워도 다음으로 넘어갑니다."""
    user, _ = a_room(session)
    session.add(Preference(user_id=user.id))
    session.commit()

    saved = session.exec(select(Preference).where(Preference.user_id == user.id)).one()
    assert saved.day_start_min is None
    assert saved.dayparts is None


def test_한_사람이_한_방에_두_번_들어올_수_없다(session: Session) -> None:
    user, room = a_room(session)
    session.add_all(
        [
            Membership(room_id=room.id, user_id=user.id),
            Membership(room_id=room.id, user_id=user.id),
        ]
    )
    with pytest.raises(REJECTED):
        session.flush()


def test_팀장은_room에만_있다(session: Session) -> None:
    """팀장이 바뀌지 않기로 했으므로 membership에 role 열을 두지 않는다.

    두 곳에 두면 서로 어긋날 수 있고, leader_user_id는 NOT NULL이라
    팀장이 정확히 한 명임을 DB가 보장한다.
    """
    user, room = a_room(session)
    session.add(Membership(room_id=room.id, user_id=user.id, part="자료조사"))
    session.commit()

    assert room.leader_user_id == user.id
    assert "role" not in Membership.model_fields


def test_시연_시계를_옮기고_되돌릴_수_있다(session: Session) -> None:
    """모든 판정의 기준 시각이다. 환경변수가 아니라 DB 한 행에 있다."""
    session.add(DemoState(id=1, now_at=None))
    session.flush()

    moved = demo_clock.set_clock(session, at(2026, 11, 12, 15))
    assert demo_clock.now(session) == moved

    demo_clock.clear_clock(session)
    # 되돌리면 실제 시각이 나온다. 옮겨 둔 2026년 값이 아니다.
    assert demo_clock.now(session) != moved


def test_오프셋_없는_시각으로는_시계를_옮길_수_없다(session: Session) -> None:
    """명세 권장 규칙 2. naive가 섞이면 늦음 판정이 조용히 어긋난다."""
    session.add(DemoState(id=1, now_at=None))
    session.flush()

    with pytest.raises(ValueError):
        demo_clock.set_clock(session, datetime(2026, 11, 12, 15))


def test_시계를_안_옮기면_지금은_aware다(session: Session) -> None:
    session.add(DemoState(id=1, now_at=None))
    session.flush()

    assert demo_clock.now(session).tzinfo is not None
