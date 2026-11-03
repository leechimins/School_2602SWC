"""시드가 시연의 전제를 만족하는지 본다.

시드는 그냥 더미 데이터가 아니다. 시연의 핵심 대사가 시드에 걸려 있다.
누가 나중에 "숫자 좀 정리하자"며 현우의 양보 점수를 0으로 만들면 2라운드
대사가 사라지는데, 그걸 시연 당일에 알게 되면 늦다.
"""

from __future__ import annotations

from datetime import date

from sqlmodel import Session, func, select

from app.me.models import Preference, ScheduleItem
from app.meeting.models import Meeting, YieldEntry
from app.shared.enums import MeetingStatus, ScheduleKind
from app.shared.models import Membership, Room, User
from tools.seed import seed


def test_팀원_네_명이_들어온다(session: Session) -> None:
    seed(session)

    names = set(session.exec(select(User.name)).all())
    assert names == {"지수", "민지", "현우", "서연"}
    assert session.exec(select(func.count()).select_from(Membership)).one() == 4


def test_마감은_12월_11일이다(session: Session) -> None:
    """마감 디데이의 유일한 기준. 홈과 일정 화면의 '남은 날'이 여기서 나온다."""
    seed(session)

    room = session.exec(select(Room)).one()
    assert room.due_date == date(2026, 12, 11)
    assert room.start_date <= room.due_date


def test_현우의_양보_점수_3이_서로_다른_회의_두_건에서_나온다(
    session: Session,
) -> None:
    """시연의 핵심 대사가 여기 걸려 있다.

    2라운드에서 "현우는 지난 두 번의 회의에서 많이 맞춰 줬어요"가 나와야
    한다. 한 회의에 +3을 몰아넣으면 "두 번"이 거짓이 된다.
    """
    seed(session)

    hyunwoo = session.exec(select(User).where(User.name == "현우")).one()
    membership = session.exec(
        select(Membership).where(Membership.user_id == hyunwoo.id)
    ).one()
    entries = session.exec(
        select(YieldEntry).where(YieldEntry.user_id == hyunwoo.id)
    ).all()

    assert membership.yield_total == 3
    assert sum(entry.points for entry in entries) == 3
    assert len({entry.meeting_id for entry in entries}) == 2, "회의 두 건이어야 한다"


def test_다른_팀원은_양보_점수가_없다(session: Session) -> None:
    seed(session)

    others = session.exec(
        select(Membership).join(User).where(User.name != "현우")
    ).all()
    assert [m.yield_total for m in others] == [0, 0, 0]


def test_현우는_평일_저녁에_알바가_있다(session: Session) -> None:
    """저녁 후보가 실제로 불편해지는 근거. 없으면 조율이 저녁을 고른다."""
    seed(session)

    hyunwoo = session.exec(select(User).where(User.name == "현우")).one()
    shifts = session.exec(
        select(ScheduleItem).where(
            ScheduleItem.user_id == hyunwoo.id,
            ScheduleItem.kind == ScheduleKind.PARTTIME,
        )
    ).all()

    assert len(shifts) == 5, "월~금 다섯 행"
    assert {shift.weekday for shift in shifts} == {0, 1, 2, 3, 4}
    assert all(shift.start_min == 18 * 60 for shift in shifts)
    # 묶음 하나로 묶여 있어야 '묶인 일정 고치기'가 한 번에 된다.
    assert len({shift.group_id for shift in shifts}) == 1


def test_민지는_오전이_수업으로_막혀_있다(session: Session) -> None:
    """민지의 '오전은 어렵다'가 말뿐이 아니라 시간표로도 참이어야 한다."""
    seed(session)

    minji = session.exec(select(User).where(User.name == "민지")).one()
    classes = session.exec(
        select(ScheduleItem).where(
            ScheduleItem.user_id == minji.id,
            ScheduleItem.kind == ScheduleKind.CLASS,
        )
    ).all()

    assert len(classes) >= 5, "수업이 많은 사람"
    mornings = [c for c in classes if c.start_min is not None and c.start_min < 12 * 60]
    assert len(mornings) >= 3


def test_피하고_싶은_시간은_다듬은_문장이_함께_있다(session: Session) -> None:
    """조율 때 말하는 건 원문이 아니라 다듬은 쪽이다."""
    seed(session)

    with_avoid = session.exec(
        select(Preference).where(Preference.avoid_raw.is_not(None))
    ).all()

    assert with_avoid, "적어도 한 사람은 피하고 싶은 시간이 있어야 조율에 이유가 선다"
    for pref in with_avoid:
        assert pref.avoid_polished
        assert pref.avoid_polished != pref.avoid_raw


def test_지난_회의_두_건이_방_기간_안에_있다(session: Session) -> None:
    seed(session)

    room = session.exec(select(Room)).one()
    past = session.exec(
        select(Meeting).where(Meeting.status == MeetingStatus.DONE)
    ).all()

    assert len(past) == 2
    for meeting in past:
        assert room.start_date <= meeting.start_at.date() <= room.due_date
        assert meeting.confirmed_at is not None
        assert meeting.rationale, "왜 이 시간이었는지가 남아 있어야 한다"
