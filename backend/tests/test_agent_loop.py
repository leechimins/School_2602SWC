"""라운드 규칙. **LLM을 끄고 돈다.**

여기서 보는 것은 "에이전트가 어떤 시간을 고르는가"다. 그 판단은 점수가
하고 모델은 말만 쓴다 — 그래서 모델 없이 전부 테스트할 수 있고, 그게
리허설과 본 시연이 같은 답을 낸다는 보장이기도 하다.

흐름(브리프 11/5): 팀원이 각자 원하는 시간을 어필 → 판단이 그중에서 고름
→ 수락·거절. 3라운드 안에 안 되면 판단이 전체에서 정하고 **바로 확정**한다.
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
    YieldEntry,
)
from app.notice.models import Notification
from app.shared.base import KST
from app.shared.enums import (
    MeetingStatus,
    NotificationKind,
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
    """팀장 지수(양보 0) + 팀원 현우(양보 3)."""
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
    점수: dict[int, int],
    못_오는_사람: int | None = None,
) -> CandidateSlot:
    """점수를 손으로 박아 둔다. 채점기는 test_slots.py가 본다."""
    slot = CandidateSlot(
        scheduling_id=scheduling.id,  # type: ignore[arg-type]
        start_at=MON.replace(hour=hour),
        end_at=MON.replace(hour=hour + 2),
        total_cost=float(sum(점수.values())),
        phase=(
            SchedulingPhase.ABSENT if 못_오는_사람 else SchedulingPhase.ALL
        ),
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
                reason=(
                    "알바와 겹칩니다"
                    if user_id == 못_오는_사람
                    else "비어 있는 시간입니다"
                ),
            )
        )
    session.commit()
    return slot


# ── 라운드는 어필에서 시작한다 ──────────────────────────────────────


def test_팀원이_먼저_원하는_시간을_말한다(session: Session, 방: 팀) -> None:
    """브리프 11/5: 판단이 아니라 팀원이 먼저 말한다."""
    s = _조율(session, 방)
    _후보(session, s, hour=14, 점수={방.지수.id: 1, 방.현우.id: 3})  # type: ignore[dict-item]

    발언 = list(run_rounds(session, s))

    assert 발언[0].speaker_kind == SpeakerKind.MEMBER
    assert "제일 좋아요" in 발언[0].text
    # 어필 둘 → 판단 하나 → 반응 둘
    assert [u.speaker_kind for u in 발언] == [
        SpeakerKind.MEMBER,
        SpeakerKind.MEMBER,
        SpeakerKind.JUDGE,
        SpeakerKind.MEMBER,
        SpeakerKind.MEMBER,
    ]


def test_전원이_조금_이하면_1라운드에_합의한다(session: Session, 방: 팀) -> None:
    s = _조율(session, 방)
    _후보(session, s, hour=14, 점수={방.지수.id: 1, 방.현우.id: 3})  # type: ignore[dict-item]

    발언 = list(run_rounds(session, s))

    assert s.status == SchedulingStatus.AGREED
    assert s.rounds_used == 1
    assert [u.seq for u in 발언] == list(range(1, len(발언) + 1))


def test_많이_불편한_사람이_있으면_다음_라운드로_간다(
    session: Session, 방: 팀
) -> None:
    """4점이 거절선이다. 브리프의 괜찮음/조금/많이와 1:1이다."""
    assert REJECT_AT == 4
    s = _조율(session, 방)
    _후보(session, s, hour=10, 점수={방.지수.id: 1, 방.현우.id: REJECT_AT})  # type: ignore[dict-item]
    편한것 = _후보(session, s, hour=16, 점수={방.지수.id: 3, 방.현우.id: 3})  # type: ignore[dict-item]

    list(run_rounds(session, s))

    assert s.status == SchedulingStatus.AGREED
    assert s.rounds_used == 2
    assert session.exec(select(Meeting)).one().start_at == 편한것.start_at


def test_거절당한_후보에도_제안_표시가_남는다(session: Session, 방: 팀) -> None:
    """시연에서 "왜 이 시간이죠"에 열어 보여 줄 근거다.

    둘 다 누군가 거절하게 둬서 라운드를 두 번 돌게 한다.
    """
    s = _조율(session, 방)
    _후보(session, s, hour=10, 점수={방.지수.id: 1, 방.현우.id: 5})  # type: ignore[dict-item]
    _후보(session, s, hour=16, 점수={방.지수.id: 5, 방.현우.id: 1})  # type: ignore[dict-item]

    list(run_rounds(session, s))

    제안된것 = session.exec(
        select(CandidateSlot).where(col(CandidateSlot.proposed).is_(True))
    ).all()
    assert len(제안된것) == 2


# ── 합의 ────────────────────────────────────────────────────────────


def test_합의하면_회의와_응답칸이_생긴다(session: Session, 방: 팀) -> None:
    """팀원 수만큼 pending을 깔아 둬야 "누가 아직 안 답했는지"를 보여 준다."""
    s = _조율(session, 방)
    _후보(session, s, hour=14, 점수={방.지수.id: 1, 방.현우.id: 1})  # type: ignore[dict-item]

    list(run_rounds(session, s))

    meeting = session.exec(select(Meeting)).one()
    assert meeting.status == MeetingStatus.PROPOSED
    assert meeting.confirmed_at is None  # 아직 확정이 아니다
    assert meeting.rationale

    응답 = session.exec(select(MeetingResponse)).all()
    assert len(응답) == 2
    assert all(r.state == ResponseState.PENDING for r in 응답)

    # 합의에는 양보 점수가 붙지 않는다. 확정될 때 붙는다.
    assert session.exec(select(YieldEntry)).all() == []


# ── 조정 — 바로 확정 ────────────────────────────────────────────────


def test_세_라운드_실패하면_조정해서_바로_확정한다(
    session: Session, 방: 팀
) -> None:
    """브리프 11/5: 수락·거절 없이 확정. 3라운드까지 돌고도 안 되면 팀플이 멈춘다."""
    s = _조율(session, 방)
    for hour in (10, 12, 14):
        _후보(session, s, hour=hour, 점수={방.지수.id: 1, 방.현우.id: 5})  # type: ignore[dict-item]

    list(run_rounds(session, s))

    assert s.status == SchedulingStatus.SETTLED
    meeting = session.exec(select(Meeting)).one()
    assert meeting.status == MeetingStatus.CONFIRMED
    assert meeting.confirmed_at is not None
    # 응답칸은 accepted로 깔린다 — 시스템이 대신 수락했고, 거기에 피드백
    # 한 줄을 받는다(브리프 11/5의 B안).
    응답 = session.exec(select(MeetingResponse)).all()
    assert len(응답) == 2
    assert all(r.state == ResponseState.ACCEPTED for r in 응답)
    assert all(r.feedback is None for r in 응답)


def test_전원_가능한_후보가_없으면_바로_조정한다(session: Session, 방: 팀) -> None:
    """라운드를 돌 대상이 없다. 1명 불참안으로 바로 간다."""
    s = _조율(session, 방)
    _후보(
        session,
        s,
        hour=18,
        점수={방.지수.id: 1, 방.현우.id: 5},  # type: ignore[dict-item]
        못_오는_사람=방.현우.id,
    )

    발언 = list(run_rounds(session, s))

    assert s.status == SchedulingStatus.SETTLED
    assert s.rounds_used <= 1
    # 판단 에이전트가 왜 이렇게 됐는지 말한다.
    assert 발언[-1].speaker_kind == SpeakerKind.JUDGE
    assert "확정" in 발언[-1].text


def test_후보가_없으면_failed다(session: Session, 방: 팀) -> None:
    s = _조율(session, 방)
    assert list(run_rounds(session, s)) == []
    assert s.status == SchedulingStatus.FAILED
    assert session.exec(select(Meeting)).all() == []


def test_조정은_거절할_사람이_적은_쪽을_먼저_고른다(
    session: Session, 방: 팀
) -> None:
    """조정은 누군가의 거절을 꺾는 일이다. 적게 꺾는 쪽이 낫다 —
    양보 가중 합이 조금 나빠도 둘을 꺾으면 회의가 거의 확실히 깨진다.
    """
    s = _조율(session, 방)
    # 셋을 돌려 라운드를 소진시킨다. 하나는 둘 다 거절, 하나는 한 명만.
    둘다거절 = _후보(session, s, hour=10, 점수={방.지수.id: 5, 방.현우.id: 5})  # type: ignore[dict-item]
    한명만 = _후보(session, s, hour=12, 점수={방.지수.id: 1, 방.현우.id: 5})  # type: ignore[dict-item]
    _후보(session, s, hour=14, 점수={방.지수.id: 4, 방.현우.id: 4})  # type: ignore[dict-item]

    list(run_rounds(session, s))

    정해진것 = session.exec(select(Meeting)).one()
    assert 정해진것.start_at == 한명만.start_at
    assert 정해진것.start_at != 둘다거절.start_at


# ── 양보 점수 ───────────────────────────────────────────────────────


def test_조정으로_맞춰_준_사람에게_양보_점수가_쌓인다(
    session: Session, 방: 팀
) -> None:
    """브리프: 조금 불편(2~3) +1, 많이 불편(4~5) +2, 괜찮음(1)은 안 받음."""
    s = _조율(session, 방)
    for hour in (10, 12, 14):
        _후보(session, s, hour=hour, 점수={방.지수.id: 1, 방.현우.id: 5})  # type: ignore[dict-item]

    list(run_rounds(session, s))

    entries = {e.user_id: e for e in session.exec(select(YieldEntry)).all()}
    # 현우는 5점(많이) → +2. 지수는 1점(괜찮음) → 행이 없다.
    assert set(entries) == {방.현우.id}
    assert entries[방.현우.id].points == 2
    assert entries[방.현우.id].discomfort == 5

    # 누적도 같은 트랜잭션에서 올라간다. 안 올리면 다음 조율의 차등이 안 생긴다.
    현우_멤버십 = session.exec(
        select(Membership).where(Membership.user_id == 방.현우.id)
    ).one()
    assert 현우_멤버십.yield_total == 3 + 2


def test_못_오는_사람은_양보_점수를_받지_않는다(session: Session, 방: 팀) -> None:
    """빠지는 것은 맞춰 주는 것이 아니다."""
    s = _조율(session, 방)
    _후보(
        session,
        s,
        hour=18,
        점수={방.지수.id: 1, 방.현우.id: 5},  # type: ignore[dict-item]
        못_오는_사람=방.현우.id,
    )

    list(run_rounds(session, s))

    assert session.exec(select(YieldEntry)).all() == []


# ── 발언 ────────────────────────────────────────────────────────────


def test_LLM이_없어도_발언이_나온다(session: Session, 방: 팀) -> None:
    """시연 당일 네트워크가 막히면 이게 유일한 길이다."""
    s = _조율(session, 방)
    _후보(session, s, hour=14, 점수={방.지수.id: 1, 방.현우.id: 3})  # type: ignore[dict-item]

    발언 = list(run_rounds(session, s))

    assert all(u.text.strip() for u in 발언)
    assert any("비어 있는 시간입니다" in u.text for u in 발언)
    assert any("11월 9일(월)" in u.text for u in 발언)


def test_판단_에이전트는_사람이_없고_팀원은_있다(session: Session, 방: 팀) -> None:
    """DB CHECK(ck_utt_speaker_shape)가 막는 모양을 실제로 지키는지."""
    s = _조율(session, 방)
    _후보(session, s, hour=14, 점수={방.지수.id: 1, 방.현우.id: 1})  # type: ignore[dict-item]

    for u in run_rounds(session, s):
        if u.speaker_kind == SpeakerKind.JUDGE:
            assert u.speaker_user_id is None
        else:
            assert u.speaker_user_id is not None


def test_상관없음으로_열면_회의_방식을_정해_준다(session: Session, 방: 팀) -> None:
    """meeting.mode에는 any가 들어갈 수 없다(CHECK). 선호로 정한다."""
    s = _조율(session, 방, mode=Mode.ANY)
    _후보(session, s, hour=14, 점수={방.지수.id: 1, 방.현우.id: 1})  # type: ignore[dict-item]

    list(run_rounds(session, s))

    assert session.exec(select(Meeting)).one().mode in (Mode.OFFLINE, Mode.ONLINE)


def test_발언이_쌓인_순서대로_남는다(session: Session, 방: 팀) -> None:
    """SSE가 끊겼다 들어와도 처음부터 다시 볼 수 있어야 한다."""
    s = _조율(session, 방)
    _후보(session, s, hour=10, 점수={방.지수.id: 1, 방.현우.id: 5})  # type: ignore[dict-item]
    _후보(session, s, hour=16, 점수={방.지수.id: 2, 방.현우.id: 2})  # type: ignore[dict-item]

    list(run_rounds(session, s))

    쌓인것 = session.exec(
        select(Utterance).order_by(col(Utterance.seq))
    ).all()
    assert [u.seq for u in 쌓인것] == list(range(1, len(쌓인것) + 1))
    assert 쌓인것[0].round_no == 1
    assert 쌓인것[-1].round_no >= 1


def test_한_번만_돌고_조정이면_한_번이라고_말한다(
    session: Session, 방: 팀
) -> None:
    """전원 가능한 후보가 하나뿐인데 거절당하면 2라운드에 쓸 것이 없다.

    그래도 전에는 발언과 알림이 둘 다 "세 번 돌았지만"이라고 했다. 시연
    레시피 중 "수요일만 2시간"이 정확히 이 경우라 화면에 그대로 나갔다.
    """
    s = _조율(session, 방)
    # 현우가 5점이라 거절한다(REJECT_AT = 4). 전원 가능한 후보는 이것 하나다.
    _후보(session, s, hour=10, 점수={방.지수.id: 1, 방.현우.id: 5})  # type: ignore[dict-item]

    list(run_rounds(session, s))

    session.refresh(s)
    assert s.rounds_used == 1
    assert s.status == SchedulingStatus.SETTLED

    판단 = session.exec(
        select(Utterance)
        .where(Utterance.speaker_kind == SpeakerKind.JUDGE)
        .order_by(col(Utterance.seq).desc())
    ).first()
    assert 판단 is not None
    assert "한 번 돌았지만" in 판단.text, 판단.text
    assert "세 번" not in 판단.text

    알림 = session.exec(
        select(Notification).where(
            Notification.kind == NotificationKind.MEETING_CONFIRMED
        )
    ).first()
    assert 알림 is not None
    assert "한 번 조율했지만" in 알림.reason, 알림.reason


def test_전원_가능한_후보가_없으면_라운드_수를_말하지_않는다(
    session: Session, 방: 팀
) -> None:
    """이 길은 라운드를 한 번도 안 돈다. "조율했지만"이라고 하면 거짓이다."""
    s = _조율(session, 방)
    _후보(
        session,
        s,
        hour=10,
        점수={방.지수.id: 1, 방.현우.id: 5},  # type: ignore[dict-item]
        못_오는_사람=방.현우.id,
    )

    list(run_rounds(session, s))

    # rounds_used는 0이 아니다 — 조정 발언이 1라운드 자리에 붙으며 1로 올린다.
    # 그래서 알림 문구가 rounds_used를 읽으면 이 길을 "한 번 돌았다"로 오해한다.
    # 조정 발언 전에 센 값을 넘기는 이유가 이 테스트다.
    알림 = session.exec(
        select(Notification).where(
            Notification.kind == NotificationKind.MEETING_CONFIRMED
        )
    ).first()
    assert 알림 is not None
    assert "모두가 가능한 시간이 없어" in 알림.reason
    assert "조율했지만" not in 알림.reason
