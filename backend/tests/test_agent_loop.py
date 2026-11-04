"""라운드 규칙. **LLM을 끄고 돈다.**

여기서 보는 것은 "에이전트가 어떤 시간을 고르는가"다. 그 판단은 점수가
하고 모델은 말만 쓴다 — 그래서 모델 없이 전부 테스트할 수 있고, 그게
리허설과 본 시연이 같은 답을 낸다는 보장이기도 하다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlmodel import Session, col, select

from app.meeting.agent_loop import REJECT_AT, run_rounds
from app.meeting.models import (
    CandidateSlot,
    Meeting,
    MeetingResponse,
    Scheduling,
    SlotCost,
    Utterance,
)
from app.shared.base import KST
from app.shared.enums import (
    MeetingStatus,
    Mode,
    ResponseState,
    SchedulingPhase,
    SchedulingStatus,
    SpeakerKind,
)
from app.shared.models import Membership, Room, User

MON = datetime(2026, 11, 9, 9, 0, tzinfo=KST)


@pytest.fixture(autouse=True)
def LLM을_끈다(monkeypatch: pytest.MonkeyPatch) -> None:
    """준비된 문장으로 떨어지는 길만 본다. 실제 호출이 나가지 않는다."""
    monkeypatch.setenv("LLM_ENABLED", "false")


class 팀:
    def __init__(self, room: Room, 지수: User, 현우: User) -> None:
        self.room = room
        self.지수 = 지수  # 팀장
        self.현우 = 현우


@pytest.fixture
def 방(session: Session) -> 팀:
    지수, 현우 = User(name="지수"), User(name="현우")
    session.add_all([지수, 현우])
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
            Membership(room_id=room.id, user_id=현우.id, yield_total=3),  # type: ignore[arg-type]
        ]
    )
    session.commit()
    return 팀(room, 지수, 현우)


def _조율(session: Session, 방: 팀, mode: Mode = Mode.ANY) -> Scheduling:
    s = Scheduling(
        room_id=방.room.id,  # type: ignore[arg-type]
        started_by=방.지수.id,  # type: ignore[arg-type]
        topic="중간 발표 준비",
        window_start=MON,
        window_end=MON + timedelta(days=4),
        duration_min=120,
        mode=mode,
        status=SchedulingStatus.RUNNING,
    )
    session.add(s)
    session.flush()
    return s


def _후보(
    session: Session,
    scheduling: Scheduling,
    *,
    hour: int,
    phase: SchedulingPhase = SchedulingPhase.ALL,
    점수: dict[int, int],
    못_오는_사람: int | None = None,
) -> CandidateSlot:
    """점수를 손으로 박아 둔다. 채점기는 test_slots.py가 본다."""
    slot = CandidateSlot(
        scheduling_id=scheduling.id,  # type: ignore[arg-type]
        start_at=MON.replace(hour=hour),
        end_at=MON.replace(hour=hour + 2),
        total_cost=float(sum(점수.values())),
        phase=phase,
        round_no=1,
        absentee_user_id=못_오는_사람,
    )
    session.add(slot)
    session.flush()
    for user_id, score in 점수.items():
        session.add(
            SlotCost(
                candidate_slot_id=slot.id,  # type: ignore[arg-type]
                user_id=user_id,
                score=score,
                available=user_id != 못_오는_사람,
                reason="알바와 겹칩니다" if user_id == 못_오는_사람 else "비어 있는 시간입니다",
            )
        )
    session.commit()
    return slot


# ── 수락·거절은 점수가 정한다 ────────────────────────────────────────


def test_전원이_조금_이하면_1라운드에_합의한다(session: Session, 방: 팀) -> None:
    s = _조율(session, 방)
    _후보(session, s, hour=14, 점수={방.지수.id: 1, 방.현우.id: 3})  # type: ignore[dict-item]

    발언 = list(run_rounds(session, s))

    assert s.status == SchedulingStatus.AGREED
    assert s.rounds_used == 1
    # 판단 1개 + 팀원 2개
    assert len(발언) == 3
    assert 발언[0].speaker_kind == SpeakerKind.JUDGE
    assert [u.seq for u in 발언] == [1, 2, 3]


def test_많이_불편한_사람이_있으면_다음_후보로_넘어간다(
    session: Session, 방: 팀
) -> None:
    """4점이 거절선이다. 브리프의 괜찮음/조금/많이와 1:1이다."""
    assert REJECT_AT == 4
    s = _조율(session, 방)
    # 거절당할 쪽을 더 싸게 둔다 — 후보는 total_cost가 싼 것부터 꺼낸다.
    _후보(session, s, hour=10, 점수={방.지수.id: 1, 방.현우.id: REJECT_AT})  # type: ignore[dict-item]
    편한것 = _후보(session, s, hour=16, 점수={방.지수.id: 3, 방.현우.id: 3})  # type: ignore[dict-item]

    list(run_rounds(session, s))

    assert s.status == SchedulingStatus.AGREED
    assert s.rounds_used == 2
    meeting = session.exec(select(Meeting)).one()
    assert meeting.start_at == 편한것.start_at


def test_세_라운드_안에_안_되면_부재_단계로_넘어간다(
    session: Session, 방: 팀
) -> None:
    s = _조율(session, 방)
    for hour in (10, 12, 14):
        _후보(session, s, hour=hour, 점수={방.지수.id: 1, 방.현우.id: 5})  # type: ignore[dict-item]
    _후보(
        session,
        s,
        hour=18,
        phase=SchedulingPhase.ABSENT,
        점수={방.지수.id: 1, 방.현우.id: 5},  # type: ignore[dict-item]
        못_오는_사람=방.현우.id,
    )

    발언 = list(run_rounds(session, s))

    # 전원 가능한 안으로는 합의하지 못했고, 한 명 빠지는 안으로 합의했다.
    assert s.status == SchedulingStatus.NO_COMMON
    단계들 = [u.phase for u in 발언]
    assert SchedulingPhase.ALL in 단계들
    assert SchedulingPhase.ABSENT in 단계들
    # 라운드 번호는 단계마다 1부터 다시 센다.
    assert [u.round_no for u in 발언 if u.phase == SchedulingPhase.ABSENT] == [1, 1, 1]


def test_둘_다_실패하면_failed다(session: Session, 방: 팀) -> None:
    s = _조율(session, 방)
    for hour in (10, 12, 14):
        _후보(session, s, hour=hour, 점수={방.지수.id: 5, 방.현우.id: 5})  # type: ignore[dict-item]

    list(run_rounds(session, s))

    assert s.status == SchedulingStatus.FAILED
    assert session.exec(select(Meeting)).all() == []


def test_후보가_없으면_바로_failed다(session: Session, 방: 팀) -> None:
    s = _조율(session, 방)
    assert list(run_rounds(session, s)) == []
    assert s.status == SchedulingStatus.FAILED


# ── 합의가 남기는 것 ────────────────────────────────────────────────


def test_합의하면_회의안과_응답칸이_생긴다(session: Session, 방: 팀) -> None:
    """팀원 수만큼 pending을 깔아 둬야 "누가 아직 안 답했는지"를 보여 줄 수 있다."""
    s = _조율(session, 방)
    _후보(session, s, hour=14, 점수={방.지수.id: 1, 방.현우.id: 1})  # type: ignore[dict-item]

    list(run_rounds(session, s))

    meeting = session.exec(select(Meeting)).one()
    assert meeting.status == MeetingStatus.PROPOSED
    assert meeting.topic == "중간 발표 준비"
    assert meeting.rationale  # 판단 에이전트의 마지막 말이 들어간다
    assert meeting.confirmed_at is None  # 아직 확정이 아니다

    응답 = session.exec(select(MeetingResponse)).all()
    assert len(응답) == 2
    assert all(r.state == ResponseState.PENDING for r in 응답)


def test_상관없음으로_열면_회의_방식을_정해_준다(session: Session, 방: 팀) -> None:
    """meeting.mode에는 any가 들어갈 수 없다(CHECK). 선호로 정한다."""
    s = _조율(session, 방, mode=Mode.ANY)
    _후보(session, s, hour=14, 점수={방.지수.id: 1, 방.현우.id: 1})  # type: ignore[dict-item]

    list(run_rounds(session, s))

    assert session.exec(select(Meeting)).one().mode in (Mode.OFFLINE, Mode.ONLINE)


# ── 발언 ────────────────────────────────────────────────────────────


def test_LLM이_없어도_발언이_나온다(session: Session, 방: 팀) -> None:
    """시연 당일 네트워크가 막히면 이게 유일한 길이다."""
    s = _조율(session, 방)
    _후보(session, s, hour=14, 점수={방.지수.id: 1, 방.현우.id: 3})  # type: ignore[dict-item]

    발언 = list(run_rounds(session, s))

    assert all(u.text.strip() for u in 발언)
    # 채점기가 만든 한국어 근거가 발언에 살아 있다.
    assert any("비어 있는 시간입니다" in u.text for u in 발언)
    assert "11월 9일(월)" in 발언[0].text


def test_못_오는_사람의_발언에_그_이유가_들어간다(
    session: Session, 방: 팀
) -> None:
    s = _조율(session, 방)
    _후보(
        session,
        s,
        hour=18,
        phase=SchedulingPhase.ABSENT,
        점수={방.지수.id: 1, 방.현우.id: 5},  # type: ignore[dict-item]
        못_오는_사람=방.현우.id,
    )

    발언 = list(run_rounds(session, s))
    현우_말 = next(u for u in 발언 if u.speaker_user_id == 방.현우.id)
    assert "알바와 겹칩니다" in 현우_말.text
    # 판단 에이전트가 왜 부재 단계로 왔는지 짚는다.
    assert "현우" in 발언[0].text


def test_판단_에이전트는_사람이_없고_팀원은_있다(session: Session, 방: 팀) -> None:
    """DB CHECK(ck_utt_speaker_shape)가 막는 모양을 실제로 지키는지."""
    s = _조율(session, 방)
    _후보(session, s, hour=14, 점수={방.지수.id: 1, 방.현우.id: 1})  # type: ignore[dict-item]

    for u in run_rounds(session, s):
        if u.speaker_kind == SpeakerKind.JUDGE:
            assert u.speaker_user_id is None
        else:
            assert u.speaker_user_id is not None


def test_거절당한_후보에도_제안_표시가_남는다(session: Session, 방: 팀) -> None:
    """시연에서 "왜 이 시간이죠"에 열어 보여 줄 근거다.

    후보는 total_cost가 싼 것부터 꺼낸다. 그래서 같은 값으로 둘을 만들어
    1라운드가 거절되고 2라운드로 넘어가게 한다.
    """
    s = _조율(session, 방)
    거절당할것 = _후보(session, s, hour=10, 점수={방.지수.id: 1, 방.현우.id: 5})  # type: ignore[dict-item]
    _후보(session, s, hour=16, 점수={방.지수.id: 3, 방.현우.id: 3})  # type: ignore[dict-item]

    list(run_rounds(session, s))

    제안된것 = session.exec(
        select(CandidateSlot).where(col(CandidateSlot.proposed).is_(True))
    ).all()
    assert len(제안된것) == 2  # 거절당한 것도 제안은 됐다
    assert 거절당할것.id in [c.id for c in 제안된것]
