"""조율 한 번의 순서. db-설계.md §6이 그대로 이 파일이다.

지금 들어 있는 것은 **1~3번까지**다 — scheduling 한 행, 빈칸 찾기, 채점.
여기까지 LLM이 안 들어온다.

4번(라운드 1~3, 발언 쌓기)부터가 LLM이고, 공급자를 아직 안 골랐다. 그래서
status는 running으로 두고 끝낸다. 후보는 이미 DB에 있으므로 LLM이 붙으면
그걸 읽어 말로 설명하는 것부터 하면 된다.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlmodel import Session, select

from app.me.models import Preference, ScheduleItem
from app.meeting.models import CandidateSlot, Meeting, Scheduling, SlotCost
from app.meeting.schemas import SchedulingStartIn
from app.meeting.scorer import Cost, pick_order, score_slot, total_cost
from app.meeting.slots import Busy, expand_busy, find_candidates
from app.shared.enums import MeetingStatus, SchedulingStatus
from app.shared.models import Membership

# 한 라운드에 저장하는 후보 개수.
#
# 채점기는 2주 기간에서 수백 개를 만든다. 전부 저장하면 사람 수를 곱한
# slot_cost가 천 행을 넘고, 무엇보다 round_no의 뜻이 흐려진다 — 그 열은
# "몇 번째 라운드가 이걸 고려했나"지 "언젠가 고려할 수 있다"가 아니다.
# 3라운드 안에 합의가 실패했을 때 사람에게 보여 줄 후보는 2~3개면 되므로
# 다섯이면 넉넉하다.
CANDIDATES_PER_ROUND = 5


def start_scheduling(
    db: Session,
    room_id: int,
    started_by: int,
    body: SchedulingStartIn,
) -> Scheduling:
    """조율을 열고 1라운드 후보까지 만든다.

    status를 running으로 두고 끝낸다. 후보가 하나도 안 나오면 no_common이다
    — 억지로 기간을 넓히지 않는다. 넓히는 것은 팀장이 widen으로 하는
    선택이고, 서버가 몰래 하면 "왜 이 시간이죠"에 답할 수 없다.
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
    yield_totals = _yield_totals(db, room_id)

    personal_busy = expand_busy(
        _schedule_items(db, member_ids), body.window_start, body.window_end
    )
    team_busy = _confirmed_meetings_as_busy(db, room_id, body)

    found = find_candidates(
        body.window_start,
        body.window_end,
        body.duration_min,
        list(prefs.values()),
        team_busy,
    )
    scored = [
        ((start_at, end_at), score_slot(start_at, end_at, member_ids, prefs, personal_busy))
        for start_at, end_at in found
    ]
    ordered = pick_order(scored, yield_totals)

    if not ordered:
        # 전원의 가능 시간이 겹치지 않거나, 겹치는 칸이 이미 다 차 있다.
        scheduling.status = SchedulingStatus.NO_COMMON
        db.commit()
        db.refresh(scheduling)
        return scheduling

    for (start_at, end_at), costs in ordered[:CANDIDATES_PER_ROUND]:
        _save_candidate(db, scheduling.id, start_at, end_at, costs)

    db.commit()
    db.refresh(scheduling)
    return scheduling


def _save_candidate(
    db: Session,
    scheduling_id: int,
    start_at: object,
    end_at: object,
    costs: Sequence[Cost],
) -> None:
    """후보 하나 + 사람 수만큼의 불편 점수.

    absentee_user_id는 딱 한 사람만 안 될 때 채운다. 그게 1명 불참안의
    재료다. 둘 이상 안 되는 후보는 비워 둔다 — 두 명을 빼는 회의는
    브리프에 없다.
    """
    unavailable = [c.user_id for c in costs if not c.available]
    candidate = CandidateSlot(
        scheduling_id=scheduling_id,
        start_at=start_at,  # type: ignore[arg-type]
        end_at=end_at,  # type: ignore[arg-type]
        total_cost=total_cost(costs),
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


def _yield_totals(db: Session, room_id: int) -> dict[int, int]:
    rows = db.exec(select(Membership).where(Membership.room_id == room_id))
    return {row.user_id: row.yield_total for row in rows.all()}


def _confirmed_meetings_as_busy(
    db: Session, room_id: int, body: SchedulingStartIn
) -> list[Busy]:
    """이미 확정된 팀 회의. 팀 전체가 묶이므로 후보에서 아예 뺀다.

    schedule_item에 회의를 넣지 않는 이유가 여기 있다 — 같은 걸 두 곳에
    쓰면 반드시 어긋나고, 빈칸 찾기가 그걸 제일 먼저 밟는다(me/models.py).
    """
    rows = db.exec(
        select(Meeting).where(
            Meeting.room_id == room_id,
            Meeting.status == MeetingStatus.CONFIRMED,
            Meeting.start_at < body.window_end,
            Meeting.end_at > body.window_start,
        )
    )
    # user_id=0은 "팀 전체"라는 표시다. Busy는 사람별 구간이지만 확정 회의는
    # 전원이 묶이므로, 사람마다 복제하는 대신 team_busy로 따로 넘긴다.
    return [Busy(0, m.start_at, m.end_at, "팀 회의") for m in rows.all()]
