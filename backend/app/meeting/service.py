"""조율 한 번의 순서. db-설계.md §6이 그대로 이 파일이다.

여기 있는 것은 **1~3번**이다 — scheduling 한 행, 빈칸 찾기, 채점. LLM이
안 들어온다. 4번부터(라운드, 발언)는 agent_loop.py이고, 거기서도 계산이
정한 결과를 LLM이 말로 옮기기만 한다.

burden()은 계산이 아니라 내보내기 규칙이라 scorer가 아니라 여기 있다 —
room/service.py의 yield_level()과 같은 자리다.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlmodel import Session, col, select

from app.me.models import Preference, ScheduleItem
from app.meeting.agent_loop import yield_totals
from app.meeting.models import CandidateSlot, Meeting, Scheduling, SlotCost
from app.meeting.schemas import SchedulingStartIn
from app.meeting.scorer import (
    Cost,
    pick_order,
    score_slot,
    total_cost,
    unavailable_count,
)
from app.meeting.slots import Busy, expand_busy, find_candidates, group_by_user
from app.shared.enums import (
    Burden,
    MeetingStatus,
    SchedulingPhase,
    SchedulingStatus,
)
from app.shared.models import Membership

# 한 라운드에 저장하는 후보 개수.
#
# 채점기는 2주 기간에서 수백 개를 만든다. 전부 저장하면 사람 수를 곱한
# slot_cost가 천 행을 넘고, 무엇보다 round_no의 뜻이 흐려진다 — 그 열은
# "몇 번째 라운드가 이걸 고려했나"지 "언젠가 고려할 수 있다"가 아니다.
# 3라운드 안에 합의가 실패했을 때 사람에게 보여 줄 후보는 2~3개면 되므로
# 다섯이면 넉넉하다.
CANDIDATES_PER_ROUND = 5

# 남의 불편을 세 단계로 뭉갤 때의 경계. 1 = 괜찮음, 2~3 = 조금, 4~5 = 많이.
#
# 양보 점수 차등(2~3 → +1, 4~5 → +2)과 거절선(agent_loop.REJECT_AT = 4)이
# 같은 자리에서 갈린다. 세 군데가 같은 경계를 쓰는 것이 우연이 아니라서
# 상수로 뺐다 — "많이 불편"은 거절할 만하고 양보 점수를 두 배로 받는 구간이다.
BURDEN_MUCH_FROM = 4
BURDEN_SOME_FROM = 2


def burden(score: int) -> Burden:
    """내 점수를 남에게 보일 단계로 바꾼다(명세 권장 규칙 3)."""
    if score >= BURDEN_MUCH_FROM:
        return Burden.MUCH
    if score >= BURDEN_SOME_FROM:
        return Burden.SOME
    return Burden.OK


def start_scheduling(
    db: Session,
    room_id: int,
    started_by: int,
    body: SchedulingStartIn,
) -> Scheduling:
    """조율을 열고 두 단계의 후보를 만든다.

    status를 running으로 두고 끝낸다. 끝 상태는 라운드 루프가 정한다.

    억지로 기간을 넓히지 않는다. 넓히는 것은 팀장이 더 넓은 기간으로 조율을
    새로 여는 선택이고, 서버가 몰래 하면 "왜 이 시간이죠"에 답할 수 없다.
    """
    scheduling = Scheduling(
        room_id=room_id,
        started_by=started_by,
        topic=body.topic,
        window_start=body.window_start,
        window_end=body.window_end,
        duration_min=body.duration_min,
        mode=body.mode,
        status=SchedulingStatus.RUNNING,
        rounds_used=0,  # 라운드는 에이전트가 말을 할 때 올라간다
    )
    db.add(scheduling)
    # id가 필요하다. candidate_slot이 이걸 FK로 잡는다.
    db.flush()
    assert scheduling.id is not None

    member_ids = _member_ids(db, room_id)
    prefs = _preferences(db, member_ids)
    yields = yield_totals(db, room_id)

    personal_busy = expand_busy(
        _schedule_items(db, member_ids), body.window_start, body.window_end
    )
    team_busy = _booked_meetings_as_busy(db, room_id, body)

    found = find_candidates(
        body.window_start,
        body.window_end,
        body.duration_min,
        list(prefs.values()),
        team_busy,
    )
    busy_by_user = group_by_user(personal_busy)
    scored = [
        ((start_at, end_at), score_slot(start_at, end_at, member_ids, prefs, busy_by_user))
        for start_at, end_at in found
    ]
    # 두 명 이상 못 오는 후보는 버린다. 브리프에 1명 불참안만 있다 — 두 명을
    # 빼는 회의는 제안할 수 없으므로, 저장하면 라운드가 쓸 수 없는 행만 쌓인다.
    usable = [pair for pair in scored if unavailable_count(pair[1]) <= 1]
    ordered = pick_order(usable, yields)

    # 두 단계를 한꺼번에 만들어 둔다. all에서 3라운드 안에 합의가 안 되면
    # 라운드 루프가 absent 쪽을 꺼내 쓴다 — 그때 다시 계산하지 않는다.
    everyone = [p for p in ordered if unavailable_count(p[1]) == 0]
    one_out = [p for p in ordered if unavailable_count(p[1]) == 1]
    # 팀장이 못 오는 후보는 맨 뒤로. "팀장은 최대한 포함"이 11/4의 결정이다.
    # 안정 정렬이라 같은 묶음 안의 불편 순서는 그대로 남는다.
    one_out.sort(key=lambda pair: _absentee_is(pair[1], started_by))

    for phase, pairs in (
        (SchedulingPhase.ALL, everyone),
        (SchedulingPhase.ABSENT, one_out),
    ):
        for (start_at, end_at), costs in pairs[:CANDIDATES_PER_ROUND]:
            _save_candidate(db, scheduling.id, phase, start_at, end_at, costs)

    # 양쪽 다 비면 라운드를 돌 것이 없다. 괜히 스트림을 열게 하지 않는다.
    # 그 밖의 끝 상태(agreed · settled · failed)는 라운드 루프가 정한다.
    if not everyone and not one_out:
        scheduling.status = SchedulingStatus.FAILED

    db.commit()
    db.refresh(scheduling)
    return scheduling


def _absentee_is(costs: Sequence[Cost], user_id: int) -> bool:
    return any(c.user_id == user_id and not c.available for c in costs)


def _save_candidate(
    db: Session,
    scheduling_id: int,
    phase: SchedulingPhase,
    start_at: object,
    end_at: object,
    costs: Sequence[Cost],
) -> None:
    """후보 하나 + 사람 수만큼의 불편 점수.

    absentee_user_id는 딱 한 사람만 안 될 때 채운다. 그게 1명 불참안의
    재료다. 두 명 이상 못 오는 후보는 부르는 쪽에서 이미 걸러진다.
    """
    unavailable = [c.user_id for c in costs if not c.available]
    candidate = CandidateSlot(
        scheduling_id=scheduling_id,
        start_at=start_at,  # type: ignore[arg-type]
        end_at=end_at,  # type: ignore[arg-type]
        total_cost=total_cost(costs),
        phase=phase,
        round_no=1,
        proposed=False,  # 판단 에이전트가 실제로 제안하면 true가 된다
        absentee_user_id=unavailable[0] if len(unavailable) == 1 else None,
    )
    db.add(candidate)
    db.flush()
    assert candidate.id is not None

    for cost in costs:
        db.add(
            SlotCost(
                candidate_slot_id=candidate.id,
                user_id=cost.user_id,
                score=cost.score,
                available=cost.available,
                reason=cost.reason,
            )
        )


def _member_ids(db: Session, room_id: int) -> list[int]:
    rows = db.exec(select(Membership.user_id).where(Membership.room_id == room_id))
    return sorted(rows.all())


def _preferences(db: Session, member_ids: Sequence[int]) -> dict[int, Preference]:
    if not member_ids:
        return {}
    rows = db.exec(select(Preference).where(Preference.user_id.in_(member_ids)))  # type: ignore[attr-defined]
    return {row.user_id: row for row in rows.all()}


def _schedule_items(db: Session, member_ids: Sequence[int]) -> list[ScheduleItem]:
    if not member_ids:
        return []
    rows = db.exec(select(ScheduleItem).where(ScheduleItem.user_id.in_(member_ids)))  # type: ignore[attr-defined]
    return list(rows.all())


def _booked_meetings_as_busy(
    db: Session, room_id: int, body: SchedulingStartIn
) -> list[Busy]:
    """이미 잡힌 팀 회의. 팀 전체가 묶이므로 후보에서 아예 뺀다.

    **확정 대기(proposed)도 센다.** 확정된 것만 보면, 1차 조율이 합의되고
    아직 아무도 수락을 안 눌렀을 때 2차 조율이 **같은 시간을 또 내놓고
    둘 다 확정될 수 있다.** 아직 답을 기다리는 회의도 그 시간을 잡아 둔
    것이 맞다.

    schedule_item에 회의를 넣지 않는 이유가 여기 있다 — 같은 걸 두 곳에
    쓰면 반드시 어긋나고, 빈칸 찾기가 그걸 제일 먼저 밟는다(me/models.py).
    """
    rows = db.exec(
        select(Meeting).where(
            Meeting.room_id == room_id,
            col(Meeting.status).in_(
                [MeetingStatus.PROPOSED, MeetingStatus.CONFIRMED]
            ),
            Meeting.start_at < body.window_end,
            Meeting.end_at > body.window_start,
        )
    )
    # user_id=0은 "팀 전체"라는 표시다. Busy는 사람별 구간이지만 확정 회의는
    # 전원이 묶이므로, 사람마다 복제하는 대신 team_busy로 따로 넘긴다.
    return [Busy(0, m.start_at, m.end_at, "팀 회의") for m in rows.all()]
