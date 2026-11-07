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
from datetime import datetime

from sqlmodel import Session, col, func, select

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
from app.meeting.prompts import Speaker, round_prompt, when, yield_step
from app.meeting.scorer import (
    Cost,
    best_for,
    pick_order,
    unavailable_count,
    yield_points,
    yield_weighted_cost,
)
from app.notice.agent_log import record
from app.shared import demo_clock, llm
from app.shared.base import KST
from app.shared.notify import emit
from app.shared.enums import (
    MeetingStatus,
    NotificationKind,
    Mode,
    ResponseState,
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
    """전원 가능한 후보로 최대 3라운드. 안 되면 전체에서 조정해 확정한다.

    라운드 한 번의 모양(브리프 11/5):
      팀원이 각자 원하는 시간을 어필 → 판단이 그중에서 고름 → 수락·거절

    끝 상태를 여기서 정한다:
      agreed   3라운드 안에 전원이 수락 → 회의(proposed)
      settled  합의 실패 또는 전원 가능한 시간 없음 → 판단이 정하고 **바로 확정**
      failed   후보가 아예 없음
    """
    assert scheduling.id is not None
    names = member_names(db, scheduling.room_id)
    yields = yield_totals(db, scheduling.room_id)
    members = sorted(names)

    # **이어 돌기.** 사람이 합의된 회의를 거절하면(rerun.reopen) 같은 조율을
    # 남은 라운드만큼 다시 돈다. 새로 시작할 때는 이미돈이 0이고 제안된 후보도
    # 없어서 아래가 전부 전과 똑같이 움직인다.
    이미돈 = scheduling.rounds_used
    세다 = _Counter(_last_seq(db, scheduling.id))
    rejections, 사람이거절한시간 = _human_rejections(db, scheduling.id, names)

    전부 = _scored(db, scheduling.id)
    제안됨 = _proposed_slots(db, scheduling.id)
    남은것 = [
        p
        for p in 전부
        if unavailable_count(p[1]) == 0
        and p[0] not in 제안됨
        and not _겹친다(p[0], 사람이거절한시간)
    ]

    for round_no in range(이미돈 + 1, MAX_ROUNDS + 1):
        if not 남은것:
            break
        appeals = _appeals(members, 남은것)
        slot = _pick_from_appeals(appeals, 남은것, yields)
        candidate = _slot_row(db, scheduling.id, slot)
        costs = _costs(db, candidate)
        speakers = _speakers(costs, names, yields)

        for u in _say(
            db,
            scheduling,
            세다,
            round_no,
            _lines(
                topic=scheduling.topic,
                candidate=candidate,
                round_no=round_no,
                speakers=speakers,
                rejections=rejections,
                appeals={names[uid]: when(*s) for uid, s in appeals.items()},
            ),
        ):
            yield u
        candidate.proposed = True
        db.add(candidate)
        db.commit()

        if all(s.accepts for s in speakers):
            _propose(db, scheduling, candidate, costs)
            return

        rejections = [f"{s.name}: {s.reason}" for s in speakers if not s.accepts]
        남은것 = [p for p in 남은것 if p[0] != slot]

    # 3라운드 실패, 또는 전원 가능한 후보가 아예 없음. 둘 다 같은 길이다 —
    # 판단 에이전트가 전체에서 고르고 바로 확정한다(브리프 11/5).
    # 사람이 거절한 시간은 조정에서도 다시 고르지 않는다. 그 사람이 싫다고 한
    # 시간을 판단 에이전트가 "바로 확정"해 버리면 거절이 아무 뜻이 없다.
    ordered = pick_order(
        [p for p in 전부 if not _겹친다(p[0], 사람이거절한시간)], yields, REJECT_AT
    )
    if not ordered:
        scheduling.status = SchedulingStatus.FAILED
        db.add(scheduling)
        db.commit()
        return

    slot, costs_tuple = ordered[0]
    candidate = _slot_row(db, scheduling.id, slot)
    costs = _costs(db, candidate)
    speakers = _speakers(costs, names, yields)
    # **조정 발언을 하기 전에** 실제로 돈 라운드 수를 적어 둔다. 조정 발언이
    # rounds_used를 1로 올리므로, 나중에 보면 "라운드가 안 돌았다"(전원 가능한
    # 후보가 없음)와 "한 번 돌았다"를 가를 수 없다.
    실제로돈 = scheduling.rounds_used
    # 0이면 발언은 1라운드 자리에 붙인다 — ck_utt_round가 1~3이다.
    돈라운드 = min(실제로돈 or 1, MAX_ROUNDS)
    for u in _say(
        db,
        scheduling,
        세다,
        돈라운드,
        [(SpeakerKind.JUDGE, None, _settle_line(speakers, when(*slot), rejections, 돈라운드))],
    ):
        yield u
    candidate.proposed = True
    db.add(candidate)
    _confirm(db, scheduling, candidate, costs, 실제로돈)


class _Counter:
    """발언 순번. 라운드를 넘어 이어지고, 이어 돌 때는 쌓인 마지막에서 시작한다."""

    def __init__(self, start: int = 0) -> None:
        self.seq = start

    def next(self) -> int:
        self.seq += 1
        return self.seq


def _say(
    db: Session,
    scheduling: Scheduling,
    세다: _Counter,
    round_no: int,
    lines: Sequence[tuple[SpeakerKind, int | None, str]],
) -> Iterator[Utterance]:
    """발언을 하나씩 저장하고 흘려보낸다."""
    assert scheduling.id is not None
    for kind, user_id, text in lines:
        utterance = Utterance(
            scheduling_id=scheduling.id,
            round_no=round_no,
            seq=세다.next(),
            speaker_kind=kind,
            speaker_user_id=user_id,
            text=text[:500],
        )
        db.add(utterance)
        scheduling.rounds_used = round_no
        db.add(scheduling)
        db.commit()
        db.refresh(utterance)
        yield utterance


def _last_seq(db: Session, scheduling_id: int) -> int:
    """이미 쌓인 발언의 마지막 번호. 없으면 0."""
    return (
        db.exec(
            select(func.max(Utterance.seq)).where(
                Utterance.scheduling_id == scheduling_id
            )
        ).one()
        or 0
    )


def _proposed_slots(
    db: Session, scheduling_id: int
) -> set[tuple[datetime, datetime]]:
    """이미 제안된 후보. 거절됐든(에이전트든 사람이든) 다시 내놓지 않는다."""
    rows = db.exec(
        select(CandidateSlot.start_at, CandidateSlot.end_at).where(
            CandidateSlot.scheduling_id == scheduling_id,
            col(CandidateSlot.proposed).is_(True),
        )
    ).all()
    return {(start, end) for start, end in rows}


def _겹친다(
    slot: tuple[datetime, datetime], 시간들: set[tuple[datetime, datetime]]
) -> bool:
    """사람이 거절한 시간과 조금이라도 겹치는지.

    **같은 후보만 빼면 안 된다.** 후보는 30분 간격이라 서로 겹친다. 15:00–17:00을
    거절했는데 14:30–16:30을 내놓으면 거절이 아무 뜻이 없다. 거절한 시간은 그 사람
    시간표에 "바쁨"으로 들어갔지만, 저장된 후보 점수는 조율을 열 때 매긴 그대로라
    겹치는 후보에서 그 사람이 여전히 "올 수 있음"으로 나온다. 그래서 여기서 뺀다.
    """
    return any(slot[0] < end and start < slot[1] for start, end in 시간들)


def _human_rejections(
    db: Session, scheduling_id: int, names: Mapping[int, str]
) -> tuple[list[str], set[tuple[datetime, datetime]]]:
    """사람이 거절해서 취소된 회의들. (판단 에이전트에게 알릴 말, 그 시간들).

    말은 "이름: 이유" 모양이다 — 에이전트가 거절한 것과 같은 꼴이라 발언
    만드는 쪽이 구분하지 않아도 된다. 이유는 거절할 때 남긴 한 줄이고, 안
    남겼으면 기본 문장이다.
    """
    cancelled = db.exec(
        select(Meeting).where(
            Meeting.scheduling_id == scheduling_id,
            Meeting.status == MeetingStatus.CANCELLED,
        )
    ).all()
    말: list[str] = []
    시간: set[tuple[datetime, datetime]] = set()
    for meeting in cancelled:
        시간.add((meeting.start_at, meeting.end_at))
        for r in db.exec(
            select(MeetingResponse).where(
                MeetingResponse.meeting_id == meeting.id,
                MeetingResponse.state == ResponseState.DECLINED,
            )
        ).all():
            말.append(
                f"{names.get(r.user_id, '팀원')}: "
                f"{r.feedback or '그 시간은 어렵다고 했어요'}"
            )
    return 말, 시간


def _appeals(
    members: Sequence[int],
    남은것: Sequence[tuple[tuple[datetime, datetime], list[Cost]]],
) -> dict[int, tuple[datetime, datetime]]:
    """각자 가장 원하는 시간. 이게 라운드의 시작이다."""
    out: dict[int, tuple[datetime, datetime]] = {}
    for user_id in members:
        slot = best_for(user_id, 남은것)
        if slot is not None:
            out[user_id] = slot
    return out


def _pick_from_appeals(
    appeals: Mapping[int, tuple[datetime, datetime]],
    남은것: Sequence[tuple[tuple[datetime, datetime], list[Cost]]],
    yields: Mapping[int, int],
) -> tuple[datetime, datetime]:
    """어필된 것 중 팀 불편 합이 가장 낮은 것. 같으면 어필이 많은 쪽.

    어필을 득표로 세지 않는다. 후보 A가 [1,1,4,4](합 10)이고 B가
    [2,2,2,2](합 8)이면 A가 2표를 받지만 두 명이 거절한다. B가 공평하다.
    그래서 득표는 동점일 때만 가른다.
    """
    어필된것 = [p for p in 남은것 if p[0] in set(appeals.values())] or list(남은것)
    표 = {slot: list(appeals.values()).count(slot) for slot, _ in 어필된것}
    return min(
        어필된것,
        key=lambda pair: (
            yield_weighted_cost(pair[1], yields),
            -표[pair[0]],
            pair[0][0],
        ),
    )[0]


def _settle_line(
    speakers: Sequence[Speaker], slot: str, rejections: Sequence[str], rounds: int
) -> str:
    """조정을 알리는 판단 에이전트의 말. LLM 없이도 설명이 되어야 한다."""
    꺾이는사람 = _bent(speakers)
    머리 = (
        f"{_몇번(rounds)} 돌았지만 전원이 좋다고 한 시간이 없습니다."
        if rejections
        else "전원이 올 수 있는 시간이 없습니다."
    )
    if 꺾이는사람 is None:
        return f"{머리} {slot}으로 정하겠습니다. 이 시간으로 확정됩니다."
    return (
        f"{머리} {꺾이는사람.name} 님은 지금까지 {꺾이는사람.yield_step}이라, "
        f"이번엔 {꺾이는사람.name} 님이 맞춰 주는 {slot}으로 정하겠습니다. "
        "이 시간으로 확정됩니다."
    )


def _몇번(rounds: int) -> str:
    """돈 라운드 수를 사람 말로. 1 → "한 번".

    숫자를 고정으로 쓰면 거짓말이 된다. 전원 가능한 후보가 하나뿐인데 그게
    거절당하면 2라운드에 쓸 것이 없어 **한 번 돌고** 바로 조정으로 간다.
    그때 "세 번"이라고 하면 틀리고, 시연 레시피 중 하나가 정확히 이 경우다.
    """
    return {1: "한 번", 2: "두 번", 3: "세 번"}.get(rounds, f"{rounds}번")


def _bent(speakers: Sequence[Speaker]) -> Speaker | None:
    """조정으로 거절이 꺾이는 사람. 거절한 사람 중 누적 양보가 가장 적은 쪽.

    못 오는 사람은 세지 않는다 — 그 사람은 빠지는 것이고 맞춰 주는 게 아니다.
    """
    꺾일사람들 = [s for s in speakers if s.available and not s.accepts]
    if not 꺾일사람들:
        return None
    return min(꺾일사람들, key=lambda s: (s.yield_rank, s.name))


# ── 읽기 ────────────────────────────────────────────────────────────


def member_names(db: Session, room_id: int) -> dict[int, str]:
    rows = db.exec(
        select(Membership.user_id, User.name).join(
            User, col(User.id) == col(Membership.user_id)
        ).where(Membership.room_id == room_id)
    ).all()
    return {user_id: name for user_id, name in rows}


def yield_totals(db: Session, room_id: int) -> dict[int, int]:
    """방 사람들의 누적 양보 점수. 후보 순서와 회의 화면이 같은 값을 봐야 한다.

    member_names와 같은 자리에 공개로 둔다. 전에는 service·router·여기에
    글자까지 똑같은 사본이 셋 있었고, 한 군데만 고치면 조용히 어긋났다.
    """
    rows = db.exec(select(Membership).where(Membership.room_id == room_id)).all()
    return {m.user_id: m.yield_total for m in rows}


def _scored(
    db: Session, scheduling_id: int
) -> list[tuple[tuple[datetime, datetime], list[Cost]]]:
    """저장된 후보 전부를 scorer가 쓰는 모양으로 읽는다.

    service가 채점해 넣은 것을 그대로 꺼낸다 — 다시 계산하지 않는다. 그래야
    화면에 보이는 점수와 판단에 쓰는 점수가 같다.
    """
    rows = db.exec(
        select(CandidateSlot)
        .where(CandidateSlot.scheduling_id == scheduling_id)
        .order_by(col(CandidateSlot.total_cost), col(CandidateSlot.start_at))
    ).all()
    out = []
    for row in rows:
        costs = [
            Cost(c.user_id, c.score, c.available, c.reason) for c in _costs(db, row)
        ]
        out.append(((row.start_at, row.end_at), costs))
    return out


def _slot_row(
    db: Session, scheduling_id: int, slot: tuple[datetime, datetime]
) -> CandidateSlot:
    return db.exec(
        select(CandidateSlot).where(
            CandidateSlot.scheduling_id == scheduling_id,
            CandidateSlot.start_at == slot[0],
            CandidateSlot.end_at == slot[1],
        )
    ).first() or _missing(slot)


def _missing(slot: tuple[datetime, datetime]) -> CandidateSlot:
    raise RuntimeError(f"후보 행을 찾지 못했습니다: {slot}")


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
            yield_rank=yields.get(c.user_id, 0),
        )
        for c in costs
    ]


# ── 말 만들기 ───────────────────────────────────────────────────────


def _lines(
    *,
    topic: str,
    candidate: CandidateSlot,
    round_no: int,
    speakers: Sequence[Speaker],
    rejections: Sequence[str],
    appeals: Mapping[str, str],
) -> list[tuple[SpeakerKind, int | None, str]]:
    """판단 1개 + 팀원 n개. LLM이 실패하면 준비된 문장으로 떨어진다."""
    slot = when(candidate.start_at, candidate.end_at)
    answer = llm.complete_json(
        round_prompt(
            topic=topic,
            slot=slot,
            round_no=round_no,
            speakers=list(speakers),
            last_round_rejections=list(rejections),
            appeals=dict(appeals),
        )
    )
    spoken = _from_llm(answer, speakers)
    if spoken is not None:
        return spoken
    return _from_template(slot, round_no, speakers, rejections, appeals)


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
    if not isinstance(judge, str) or not judge.strip():
        return None

    어필 = _said(answer.get("appeals", []))
    반응 = _said(answer.get("responses"))
    if 반응 is None or 어필 is None:
        return None
    # 반응은 전원이 있어야 한다. 어필은 2라운드부터 비어 있는 게 정상이다.
    if any(s.user_id not in 반응 for s in speakers):
        return None

    lines: list[tuple[SpeakerKind, int | None, str]] = [
        (SpeakerKind.MEMBER, s.user_id, 어필[s.user_id])
        for s in speakers
        if s.user_id in 어필
    ]
    lines.append((SpeakerKind.JUDGE, None, judge.strip()))
    lines += [(SpeakerKind.MEMBER, s.user_id, 반응[s.user_id]) for s in speakers]
    return lines


def _said(items: object) -> dict[int, str] | None:
    """[{"user_id": 1, "text": "…"}] 를 사전으로. 모양이 틀리면 None."""
    if not isinstance(items, list):
        return None
    out: dict[int, str] = {}
    for item in items:
        if not isinstance(item, dict):
            return None
        user_id, text = item.get("user_id"), item.get("text")
        if not isinstance(user_id, int) or not isinstance(text, str):
            return None
        if text.strip():
            out[user_id] = text.strip()
    return out


def _from_template(
    slot: str,
    round_no: int,
    speakers: Sequence[Speaker],
    rejections: Sequence[str],
    appeals: Mapping[str, str],
) -> list[tuple[SpeakerKind, int | None, str]]:
    """LLM 없이 도는 길. 시연 당일 네트워크가 막혔을 때 이게 유일한 길이다.

    slot_cost.reason이 이미 사람이 읽을 한국어다("알바와 겹칩니다"). 거기에
    앞말만 붙이면 발언이 된다.
    """
    lines: list[tuple[SpeakerKind, int | None, str]] = []

    # ① 1라운드에만 각자 원하는 시간을 말한다. 2라운드부터는 판단이 먼저
    # 무엇을 바꿨는지 말해야 "어렵습니다"가 가리킬 데가 생긴다.
    #
    # 같은 시간을 어필한 사람은 "저도"로 — 넷이 똑같은 문장을 말하면
    # 화면이 지루하다.
    말한것: set[str] = set()
    if round_no == 1:
        for s in speakers:
            원한것 = appeals.get(s.name)
            if not 원한것:
                continue
            앞말 = "저도" if 원한것 in 말한것 else "저는"
            말한것.add(원한것)
            lines.append(
                (SpeakerKind.MEMBER, s.user_id, f"{앞말} {원한것}이 제일 좋아요.")
            )

    # ② 판단 에이전트가 그중에서 고른다.
    if round_no == 1:
        judge = f"{slot}으로 하겠습니다. 팀 전체로 가장 덜 불편한 시간이에요."
    else:
        앞서 = rejections[0].split(":")[0] if rejections else "한 분"
        judge = f"{앞서} 님이 어렵다고 해서 {slot}으로 바꿉니다."
    lines.append((SpeakerKind.JUDGE, None, judge))

    # ③ 수락·거절.
    for s in speakers:
        앞말 = "좋아요" if s.score == 1 else "괜찮아요" if s.accepts else "어렵습니다"
        lines.append((SpeakerKind.MEMBER, s.user_id, f"{앞말}. {s.reason}."))
    return lines


# ── 합의 ────────────────────────────────────────────────────────────


def _propose(
    db: Session,
    scheduling: Scheduling,
    candidate: CandidateSlot,
    costs: Sequence[SlotCost],
) -> None:
    """합의됐다. 회의를 만든다 — 아직 확정이 아니라 proposed다.

    팀원 수만큼 meeting_response를 pending으로 깔아 둔다. 그래야 "누가 아직
    안 답했는지"를 이름으로 보여 줄 수 있다(브리프).
    """
    meeting = _make_meeting(db, scheduling, candidate, costs, MeetingStatus.PROPOSED)
    assert meeting.id is not None
    for cost in costs:
        db.add(
            MeetingResponse(
                meeting_id=meeting.id,
                user_id=cost.user_id,
                state=ResponseState.PENDING,
            )
        )
    scheduling.status = SchedulingStatus.AGREED
    db.add(scheduling)
    _tell(
        db,
        scheduling.room_id,
        meeting.id,
        [c.user_id for c in costs],
        NotificationKind.MEETING_PROPOSED,
        f"{scheduling.topic} 회의 일정이 나왔습니다. 수락·거절해 주세요.",
    )
    record(
        db,
        scheduling.room_id,
        f"{scheduling.topic} 회의를 {_때(candidate)}으로 제안했어요",
        meeting.rationale or "팀 전체로 가장 덜 불편한 시간이에요",
    )
    db.commit()


def _confirm(
    db: Session,
    scheduling: Scheduling,
    candidate: CandidateSlot,
    costs: Sequence[SlotCost],
    rounds_ran: int,
) -> None:
    """조정됐다. **수락·거절 없이 바로 확정한다**(브리프 11/5).

    3라운드까지 돌고도 결정이 안 나면 팀플이 멈춘다. 대신 피드백 한 줄은
    받는다 — 그 길은 수락·거절 엔드포인트가 맡는다.

    오는 사람에게 meeting_response를 accepted로 깔아 둔다. 거짓이 아니다 —
    시스템이 대신 수락한 것이고, scheduling.status가 settled인 것으로 화면이
    "조정"을 안다. 이 행이 있어야 피드백 한 줄을 받을 자리가 생기고, 일정
    화면이 "사람별 응답 상태"를 그릴 수 있다.

    못 오는 사람은 만들지 않는다 — 브리프: "불참안이면 빠지는 사람은
    응답자에서 빠지고".
    """
    now = demo_clock.now(db)
    meeting = _make_meeting(db, scheduling, candidate, costs, MeetingStatus.CONFIRMED)
    meeting.confirmed_at = now
    db.add(meeting)
    assert meeting.id is not None

    for cost in costs:
        if not cost.available:
            continue
        db.add(
            MeetingResponse(
                meeting_id=meeting.id,
                user_id=cost.user_id,
                state=ResponseState.ACCEPTED,
                responded_at=now,
            )
        )

    award_yield(db, scheduling.room_id, meeting.id, costs)
    scheduling.status = SchedulingStatus.SETTLED
    db.add(scheduling)
    _tell(
        db,
        scheduling.room_id,
        meeting.id,
        [c.user_id for c in costs],
        NotificationKind.MEETING_CONFIRMED,
        f"{scheduling.topic} 회의가 확정됐습니다. {_왜조정(rounds_ran)}",
    )
    record(
        db,
        scheduling.room_id,
        f"{scheduling.topic} 회의를 {_때(candidate)}으로 정했어요",
        _왜조정(rounds_ran),
    )
    db.commit()


def _때(candidate: CandidateSlot) -> str:
    """기록에 쓸 회의 시각. 한국 시각으로 바꿔 읽는다 — DB가 다른 시간대로 돌려줘도 같은 글자가 나오게."""
    return when(candidate.start_at.astimezone(KST), candidate.end_at.astimezone(KST))


def _왜조정(rounds_ran: int) -> str:
    """조정으로 간 이유. 두 갈래를 구분해서 말한다.

    한 문장으로 뭉뚱그리면 반은 거짓이 된다. 3라운드를 돌고 실패한 경우는
    **모두 올 수는 있었고** 누군가 거절한 것이라, "모두가 가능한 시간이
    없었다"고 말하면 틀린다. 반대도 마찬가지다.

    rounds_ran은 **조정 발언 전에** 센 값이다(run_rounds). 0이면 라운드가
    한 번도 안 돈 것이고, 그건 전원 가능한 후보가 처음부터 없었다는 뜻이다.
    scheduling.rounds_used를 여기서 읽으면 안 된다 — 조정 발언이 이미 1로
    올려 놓아서 두 갈래가 구분되지 않는다.
    """
    if not rounds_ran:
        return "모두가 가능한 시간이 없어 판단 에이전트가 정했어요."
    return (
        f"{_몇번(rounds_ran)} 조율했지만 전원이 좋다고 한 시간이 없어 "
        "판단 에이전트가 정했어요."
    )


def _tell(
    db: Session,
    room_id: int,
    meeting_id: int,
    user_ids: Sequence[int],
    kind: NotificationKind,
    reason: str,
) -> None:
    """알림을 깐다. 못 오는 사람도 받는다 — 자기가 빠지는 회의라서 더 알아야 한다.

    dedupe가 회의 하나당 하나다. 같은 회의의 회의 알림과 확정 알림은
    kind가 달라 서로를 막지 않는다(shared/notify.emit이 앞에 kind를 붙인다).
    """
    emit(
        db,
        room_id=room_id,
        user_ids=user_ids,
        kind=kind,
        reason=reason[:200],
        dedupe=f"meeting{meeting_id}",
        meeting_id=meeting_id,
    )


def _make_meeting(
    db: Session,
    scheduling: Scheduling,
    candidate: CandidateSlot,
    costs: Sequence[SlotCost],
    status: MeetingStatus,
) -> Meeting:
    assert scheduling.id is not None
    scheduling.closed_at = demo_clock.now(db)
    meeting = Meeting(
        room_id=scheduling.room_id,
        scheduling_id=scheduling.id,
        topic=scheduling.topic,
        start_at=candidate.start_at,
        end_at=candidate.end_at,
        mode=_decide_mode(db, scheduling.mode, [c.user_id for c in costs]),
        status=status,
        rationale=_rationale(db, scheduling.id),
        # 회의 화면이 이걸로 slot_cost를 찾아 "내 불편 3/5"를 보여 준다.
        # 안 채우면 (scheduling_id, start_at)으로 되짚어야 한다.
        candidate_slot_id=candidate.id,
    )
    db.add(meeting)
    db.flush()
    return meeting


def award_yield(
    db: Session, room_id: int, meeting_id: int, costs: Sequence[SlotCost]
) -> None:
    """맞춰 준 사람에게 양보 점수를 올린다. 브리프의 차등 그대로다.

    조금 불편(2~3) +1, 많이 불편(4~5) +2, 괜찮음(1)은 행을 만들지 않는다.
    못 오는 사람도 받지 않는다 — 빠지는 것은 맞춰 주는 것이 아니다.

    membership.yield_total을 같은 트랜잭션에서 올린다. 그 값이 다음 조율의
    차등이 되므로 yield_entry만 쌓고 합계를 안 올리면 차등이 영원히 안 생긴다.
    """
    for cost in costs:
        points = yield_points(cost.score, cost.available)
        if not points:
            continue
        db.add(
            YieldEntry(
                room_id=room_id,
                meeting_id=meeting_id,
                user_id=cost.user_id,
                points=points,
                discomfort=cost.score,
                reason=f"내 불편 {cost.score}/5만큼 맞춰 줘서 +{points}",
            )
        )
        membership = db.exec(
            select(Membership).where(
                Membership.room_id == room_id, Membership.user_id == cost.user_id
            )
        ).first()
        if membership is not None:
            membership.yield_total += points
            db.add(membership)


def _rationale(db: Session, scheduling_id: int) -> str:
    """판단 에이전트의 마지막 말. 회의 화면이 "왜 이 시간인지"로 쓴다."""
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
