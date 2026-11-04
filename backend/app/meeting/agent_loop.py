"""라운드를 돌려 발언을 만든다. db-설계.md §6의 4~5번.

**판단은 전부 여기서 하고, 말은 전부 LLM이 한다.** 어느 후보를 제안할지,
누가 수락하고 누가 거절할지는 점수가 정한다(scorer.py). 모델은 그 결과를
사람 말로 옮기기만 한다 — 그래야 리허설과 본 시연이 같은 시간을 고른다.

제너레이터다. 발언을 하나 만들 때마다 DB에 넣고 yield한다. SSE가 그걸
그대로 흘려보내므로, 사용자는 발언이 쌓이는 것을 본다. 브리프: "이 10~20초는
로딩이 아니라 구경거리입니다."
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence

from sqlmodel import Session, col, select

from app.me.models import Preference
from app.meeting.models import (
    CandidateSlot,
    Meeting,
    MeetingResponse,
    Scheduling,
    SlotCost,
    Utterance,
)
from app.meeting.prompts import Speaker, round_prompt, when, yield_step
from app.shared import demo_clock, llm
from app.shared.enums import (
    MeetingStatus,
    Mode,
    ResponseState,
    SchedulingPhase,
    SchedulingStatus,
    SpeakerKind,
)
from app.shared.models import Membership, User

MAX_ROUNDS = 3

# 이 점수 이상이면 팀원 에이전트가 거절한다. 브리프의 말과 1:1이다 —
# 괜찮음(1)·조금(2~3)은 수락, 많이(4~5)는 거절. 브리프 예시의 "수업 바로
# 뒤라 조금 빠듯하지만 괜찮아요"가 3점이고 수락으로 떨어진다.
REJECT_AT = 4


def run_rounds(db: Session, scheduling: Scheduling) -> Iterator[Utterance]:
    """두 단계 × 최대 3라운드. 합의하면 회의안까지 만들고 멈춘다.

    끝 상태를 여기서 정한다:
      agreed     전원 가능한 안으로 합의
      no_common  한 명이 못 오는 안으로 합의
      failed     두 단계 모두 실패
    """
    assert scheduling.id is not None
    names = member_names(db, scheduling.room_id)
    yields = _yield_totals(db, scheduling.room_id)
    seq = 0
    rejections: list[str] = []

    for phase in (SchedulingPhase.ALL, SchedulingPhase.ABSENT):
        queue = _candidates(db, scheduling.id, phase)
        scheduling.rounds_used = 0

        for round_no in range(1, MAX_ROUNDS + 1):
            if not queue:
                break
            candidate = queue.pop(0)
            candidate.proposed = True
            costs = _costs(db, candidate)
            speakers = _speakers(costs, names, yields)

            for kind, user_id, text in _lines(
                topic=scheduling.topic,
                candidate=candidate,
                phase=phase,
                round_no=round_no,
                speakers=speakers,
                rejections=rejections,
            ):
                seq += 1
                utterance = Utterance(
                    scheduling_id=scheduling.id,
                    phase=phase,
                    round_no=round_no,
                    seq=seq,
                    speaker_kind=kind,
                    speaker_user_id=user_id,
                    text=text[:500],
                )
                db.add(utterance)
                scheduling.rounds_used = round_no
                db.add(scheduling)
                db.add(candidate)
                db.commit()
                db.refresh(utterance)
                yield utterance

            # 합의는 **오는 사람** 전원이 수락한 것이다. 못 오는 사람의
            # 거절까지 세면 1명 불참안은 영원히 합의되지 않는다 — 그 사람은
            # 애초에 빠지기로 한 사람이다.
            attending = [s for s in speakers if s.available]
            if attending and all(s.accepts for s in attending):
                _agree(db, scheduling, candidate, costs, phase)
                return

            rejections = [
                f"{s.name}: {s.reason}" for s in speakers if not s.accepts
            ]

    scheduling.status = SchedulingStatus.FAILED
    db.add(scheduling)
    db.commit()


# ── 읽기 ────────────────────────────────────────────────────────────


def member_names(db: Session, room_id: int) -> dict[int, str]:
    rows = db.exec(
        select(Membership.user_id, User.name).join(
            User, col(User.id) == col(Membership.user_id)
        ).where(Membership.room_id == room_id)
    ).all()
    return {user_id: name for user_id, name in rows}


def _yield_totals(db: Session, room_id: int) -> dict[int, int]:
    rows = db.exec(select(Membership).where(Membership.room_id == room_id)).all()
    return {m.user_id: m.yield_total for m in rows}


def _candidates(
    db: Session, scheduling_id: int, phase: SchedulingPhase
) -> list[CandidateSlot]:
    """제안할 순서대로. service가 이미 좋은 순으로 저장했다."""
    return list(
        db.exec(
            select(CandidateSlot)
            .where(
                CandidateSlot.scheduling_id == scheduling_id,
                CandidateSlot.phase == phase,
            )
            .order_by(col(CandidateSlot.total_cost), col(CandidateSlot.start_at))
        ).all()
    )


def _costs(db: Session, candidate: CandidateSlot) -> list[SlotCost]:
    return list(
        db.exec(
            select(SlotCost).where(SlotCost.candidate_slot_id == candidate.id)
        ).all()
    )


def _speakers(
    costs: Sequence[SlotCost],
    names: Mapping[int, str],
    yields: Mapping[int, int],
) -> list[Speaker]:
    """수락·거절을 여기서 정한다. 점수만 본다."""
    return [
        Speaker(
            user_id=c.user_id,
            name=names.get(c.user_id, "팀원"),
            score=c.score,
            available=c.available,
            reason=c.reason,
            accepts=c.available and c.score < REJECT_AT,
            yield_step=yield_step(yields.get(c.user_id, 0)),
        )
        for c in costs
    ]


# ── 말 만들기 ───────────────────────────────────────────────────────


def _lines(
    *,
    topic: str,
    candidate: CandidateSlot,
    phase: SchedulingPhase,
    round_no: int,
    speakers: Sequence[Speaker],
    rejections: Sequence[str],
) -> list[tuple[SpeakerKind, int | None, str]]:
    """판단 1개 + 팀원 n개. LLM이 실패하면 준비된 문장으로 떨어진다."""
    slot = when(candidate.start_at, candidate.end_at)
    answer = llm.complete_json(
        round_prompt(
            topic=topic,
            slot=slot,
            round_no=round_no,
            is_absent_phase=phase == SchedulingPhase.ABSENT,
            speakers=list(speakers),
            last_round_rejections=list(rejections),
        )
    )
    spoken = _from_llm(answer, speakers)
    if spoken is not None:
        return spoken
    return _from_template(slot, phase, round_no, speakers, rejections)


def _from_llm(
    answer: dict | None, speakers: Sequence[Speaker]
) -> list[tuple[SpeakerKind, int | None, str]] | None:
    """모델 답을 믿기 전에 모양을 본다.

    한 사람이라도 빠지면 통째로 버리고 템플릿을 쓴다. 섞어 쓰면 화면에
    누구는 말하고 누구는 안 하는 라운드가 나온다.
    """
    if not isinstance(answer, dict):
        return None
    judge = answer.get("judge")
    members = answer.get("members")
    if not isinstance(judge, str) or not judge.strip():
        return None
    if not isinstance(members, list):
        return None

    said: dict[int, str] = {}
    for item in members:
        if not isinstance(item, dict):
            return None
        user_id, text = item.get("user_id"), item.get("text")
        if not isinstance(user_id, int) or not isinstance(text, str):
            return None
        if text.strip():
            said[user_id] = text.strip()

    if any(s.user_id not in said for s in speakers):
        return None

    lines: list[tuple[SpeakerKind, int | None, str]] = [
        (SpeakerKind.JUDGE, None, judge.strip())
    ]
    lines += [(SpeakerKind.MEMBER, s.user_id, said[s.user_id]) for s in speakers]
    return lines


def _from_template(
    slot: str,
    phase: SchedulingPhase,
    round_no: int,
    speakers: Sequence[Speaker],
    rejections: Sequence[str],
) -> list[tuple[SpeakerKind, int | None, str]]:
    """LLM 없이 도는 길. 시연 당일 네트워크가 막혔을 때 이게 유일한 길이다.

    slot_cost.reason이 이미 사람이 읽을 한국어다("알바와 겹칩니다"). 거기에
    앞말만 붙이면 발언이 된다.
    """
    if phase == SchedulingPhase.ABSENT and round_no == 1:
        빠지는 = next((s.name for s in speakers if not s.available), "한 명")
        judge = (
            f"전원이 가능한 시간을 찾지 못했습니다. "
            f"{빠지는} 님이 빠지는 안으로 {slot}을 제안합니다."
        )
    elif round_no == 1:
        judge = f"{slot}을 제안합니다. 팀 전체로 가장 덜 불편한 시간이에요."
    else:
        앞서 = rejections[0].split(":")[0] if rejections else "한 분"
        judge = f"{앞서} 님이 어렵다고 해서 {slot}으로 바꿉니다."

    lines: list[tuple[SpeakerKind, int | None, str]] = [
        (SpeakerKind.JUDGE, None, judge)
    ]
    for s in speakers:
        앞말 = "좋아요" if s.score == 1 else "괜찮아요" if s.accepts else "어렵습니다"
        lines.append((SpeakerKind.MEMBER, s.user_id, f"{앞말}. {s.reason}."))
    return lines


# ── 합의 ────────────────────────────────────────────────────────────


def _agree(
    db: Session,
    scheduling: Scheduling,
    candidate: CandidateSlot,
    costs: Sequence[SlotCost],
    phase: SchedulingPhase,
) -> None:
    """회의안을 만든다. 아직 확정이 아니라 proposed다.

    팀원 수만큼 meeting_response를 pending으로 깔아 둔다. 그래야 "누가 아직
    안 답했는지"를 이름으로 보여 줄 수 있다(브리프).
    """
    assert scheduling.id is not None
    scheduling.status = (
        SchedulingStatus.NO_COMMON
        if phase == SchedulingPhase.ABSENT
        else SchedulingStatus.AGREED
    )
    scheduling.closed_at = demo_clock.now(db)

    meeting = Meeting(
        room_id=scheduling.room_id,
        scheduling_id=scheduling.id,
        topic=scheduling.topic,
        start_at=candidate.start_at,
        end_at=candidate.end_at,
        mode=_decide_mode(db, scheduling.mode, [c.user_id for c in costs]),
        status=MeetingStatus.PROPOSED,
        rationale=_rationale(db, scheduling.id),
    )
    db.add(meeting)
    db.flush()
    assert meeting.id is not None

    for cost in costs:
        db.add(
            MeetingResponse(
                meeting_id=meeting.id,
                user_id=cost.user_id,
                state=ResponseState.PENDING,
            )
        )
    db.add(scheduling)
    db.commit()


def _rationale(db: Session, scheduling_id: int) -> str:
    """판단 에이전트의 마지막 말. 회의안 화면이 "왜 이 시간인지"로 쓴다."""
    last = db.exec(
        select(Utterance)
        .where(
            Utterance.scheduling_id == scheduling_id,
            Utterance.speaker_kind == SpeakerKind.JUDGE,
        )
        .order_by(col(Utterance.seq).desc())
    ).first()
    return (last.text if last else "")[:500]


def _decide_mode(db: Session, asked: Mode, user_ids: Sequence[int]) -> Mode:
    """확정된 회의는 대면이나 비대면 중 하나다. any가 들어갈 수 없다(CHECK).

    팀장이 "상관없음"으로 열었으면 참석자들의 선호로 정한다. 많이 고른 쪽,
    같으면 대면 — 팀플은 기본이 만나는 것이고, 비대면은 고른 사람이 더
    많을 때만 간다.
    """
    if asked not in (Mode.ONLINE, Mode.OFFLINE):
        prefs = db.exec(
            select(Preference).where(col(Preference.user_id).in_(user_ids))
        ).all()
        online = sum(1 for p in prefs if p.mode_pref == Mode.ONLINE)
        offline = sum(1 for p in prefs if p.mode_pref == Mode.OFFLINE)
        return Mode.ONLINE if online > offline else Mode.OFFLINE
    return asked
