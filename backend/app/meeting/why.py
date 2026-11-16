"""왜 이 시간인가 — 고른 시간과 2순위를 같은 기준으로 비교해 처음 갈린 이유를 말한다.

AI가 아니라 계산이다. 조율이 저장해 둔 후보(candidate_slot)와 사람별 불편(slot_cost)을
고르는 기준(scorer.pick_order와 같은 순서)으로 다시 놓고 본다:

  1. 못 오는 사람 수        → fewer_absent
  2. 많이 불편한(4+) 사람 수 → fewer_reject
  3. 양보 가중 합           → yield_first(가중 때문에 갈림) / lower_total(합 자체가 낮음)
  4. 이른 시각              → earlier

2순위가 기준상 더 나은데도 안 골랐다면 앞 라운드에서 거절된 시간이다(rejected_before).

남의 불편은 숫자 없이 단계(괜찮음·조금·많이)로만 나간다(명세 권장 규칙 3). 이유 문장은
slot_cost.reason 그대로 — 이미 회의 화면에 팀원에게 보이는 문장이고 일정 제목은 없다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from sqlmodel import Session, select

from app.meeting.agent_loop import REJECT_AT, member_names, yield_balances
from app.meeting.models import CandidateSlot, Meeting, SlotCost
from app.meeting.schemas import WhyOut, WhyPerson
from app.meeting.scorer import Cost, rejecting_count, unavailable_count, yield_weighted_cost
from app.meeting.service import burden
from app.shared.base import KST
from app.shared.enums import Burden

_WEEKDAYS = "월화수목금토일"
_WORD = {Burden.OK: "괜찮음", Burden.SOME: "조금", Burden.MUCH: "많이"}


def _short(slot: CandidateSlot) -> str:
    """화 15:00"""
    at = slot.start_at.astimezone(KST)
    return f"{_WEEKDAYS[at.weekday()]} {at:%H:%M}"


def _costs(rows: Sequence[SlotCost]) -> list[Cost]:
    return [Cost(r.user_id, r.score, r.available, r.reason) for r in rows]


def _key(costs: Sequence[Cost], yields: Mapping[int, float], slot: CandidateSlot) -> tuple[object, ...]:
    return (
        unavailable_count(costs),
        rejecting_count(costs, REJECT_AT),
        yield_weighted_cost(costs, yields),
        slot.start_at,
    )


def _names(ids: Sequence[int], names: Mapping[int, str]) -> str:
    return "·".join(f"{names.get(i, '팀원')}님" for i in ids)


def explain(db: Session, meeting: Meeting) -> WhyOut | None:
    """회의 하나의 "왜 이 시간". 조율 없이 만든 회의·비교할 후보가 없으면 None."""
    if meeting.scheduling_id is None or meeting.candidate_slot_id is None:
        return None
    slots = list(db.exec(select(CandidateSlot).where(CandidateSlot.scheduling_id == meeting.scheduling_id)).all())
    chosen = next((s for s in slots if s.id == meeting.candidate_slot_id), None)
    if chosen is None or len(slots) < 2:
        return None

    rows: dict[int, list[SlotCost]] = {}
    for r in db.exec(select(SlotCost).where(SlotCost.candidate_slot_id.in_([s.id for s in slots]))).all():  # type: ignore[union-attr]
        rows.setdefault(r.candidate_slot_id, []).append(r)
    yields = yield_balances(db, meeting.room_id, exclude_meeting_id=meeting.id)
    names = member_names(db, meeting.room_id)

    costs = {s.id: _costs(rows.get(s.id, [])) for s in slots}  # type: ignore[index]
    others = [s for s in slots if s.id != chosen.id]
    runner = min(others, key=lambda s: _key(costs[s.id], yields, s))  # type: ignore[index]
    mine, theirs = costs[chosen.id], costs[runner.id]  # type: ignore[index]
    by_user_here = {c.user_id: c for c in mine}
    by_user_there = {c.user_id: c for c in theirs}

    a, b = _key(mine, yields, chosen), _key(theirs, yields, runner)
    here, there = _short(chosen), _short(runner)
    if a > b:
        rule = "rejected_before"
        summary = f"{here}을 골랐어요. 기준만 보면 {there}이 나았지만 앞 라운드에서 거절이 나왔어요."
    elif a[0] != b[0]:
        rule = "fewer_absent"
        absent = [c.user_id for c in theirs if not c.available]
        summary = f"{here}을 골랐어요. {there}은 {_names(absent, names)}이 올 수 없어요."
    elif a[1] != b[1]:
        rule = "fewer_reject"
        much = [c.user_id for c in theirs if c.available and c.score >= REJECT_AT]
        summary = f"{here}을 골랐어요. {there}은 {_names(much, names)}이 많이 불편한 시간이에요."
    elif a[2] != b[2]:
        raw_here = sum(c.score for c in mine if c.available)
        raw_there = sum(c.score for c in theirs if c.available)
        helped = [
            uid
            for uid, c in by_user_here.items()
            if yields.get(uid, 0) > 0 and uid in by_user_there and c.score < by_user_there[uid].score
        ]
        if raw_here >= raw_there and helped:
            rule = "yield_first"
            summary = f"{here}을 골랐어요. 불편은 {there}과 비슷하지만, 그동안 많이 맞춰 준 {_names(helped, names)}이 편한 쪽을 먼저 챙겼어요."
        else:
            rule = "lower_total"
            summary = f"{here}을 골랐어요. {there}보다 팀 전체가 덜 불편해요."
    else:
        rule = "earlier"
        summary = f"{here}을 골랐어요. {there}과 불편이 같아서 더 이른 시간으로 정했어요."

    # 고른 시간에 가장 불편한 사람 한 명은 숨기지 않고 말한다
    worst = max((c for c in mine if c.available and c.score >= 2), key=lambda c: c.score, default=None)
    if worst is not None and rule != "rejected_before":
        summary += f" 대신 {names.get(worst.user_id, '팀원')}님은 {_WORD[burden(worst.score)]} 불편해요({worst.reason})."

    people = [
        WhyPerson(
            name=names.get(uid, "팀원"),
            here=burden(c.score) if c.available else None,
            there=(
                burden(by_user_there[uid].score)
                if uid in by_user_there and by_user_there[uid].available
                else None
            ),
            reason_here=c.reason,
        )
        for uid, c in sorted(by_user_here.items())
    ]
    return WhyOut(
        chosen_start=chosen.start_at,
        chosen_end=chosen.end_at,
        runner_up_start=runner.start_at,
        runner_up_end=runner.end_at,
        rule=rule,  # type: ignore[arg-type]
        summary=summary,
        people=people,
    )
