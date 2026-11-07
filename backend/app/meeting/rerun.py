"""사람이 합의된 회의를 거절했을 때 — 조율을 다시 연다.

브리프 11/5: 거절은 **자동으로** 다시 조율한다. 팀장 승인을 기다리지 않고,
거절한 사람이 누구든 같다. 그래서 따로 엔드포인트를 두지 않고 respond가
여기를 부른다.

**새로 3라운드를 주지 않는다.** 라운드는 조율 하나에 3이 예산이다. 1라운드에
합의됐다면 2라운드가 남아 있고, 3라운드까지 다 썼다면 다시 돌지 않고 그
사람을 불참으로 둔다. 그 갈래는 respond가 맡는다.

다시 도는 것은 **같은 루프**다(agent_loop.run_rounds). 거절된 시간 하나가
후보에서 빠지고, 그 시간이 1순위였던 사람들만 어필이 바뀐다. 후보를 새로
만들거나 다시 채점하지 않는다 — 조율을 열 때 저장한 후보가 다섯이고 라운드가
최대 셋이라 남는다.
"""

from __future__ import annotations

from sqlmodel import Session

from app.me.models import ScheduleItem
from app.meeting.agent_loop import MAX_ROUNDS
from app.meeting.models import Meeting, Scheduling
from app.shared.enums import (
    MeetingStatus,
    Recurrence,
    ScheduleKind,
    ScheduleSource,
    SchedulingStatus,
)


def rounds_left(scheduling: Scheduling) -> int:
    """남은 라운드. 0이면 다시 조율하지 않는다."""
    return max(0, MAX_ROUNDS - scheduling.rounds_used)


def can_rerun(scheduling: Scheduling | None) -> bool:
    """합의된 조율에 예산이 남았을 때만. 조율 없이 만든 회의는 돌릴 것이 없다."""
    return (
        scheduling is not None
        and scheduling.status == SchedulingStatus.AGREED
        and rounds_left(scheduling) > 0
    )


def reopen(
    db: Session, scheduling: Scheduling, meeting: Meeting, decliner_id: int
) -> None:
    """옛 회의를 취소하고 조율을 다시 running으로 돌린다. 커밋은 부른 쪽이 한다.

    거절한 시간은 그 사람의 시간표에 **일회성 일정**으로 넣는다. 제목은 비운다 —
    팀에는 "바쁨"으로만 나가고, 급한 일이 무엇인지 알릴 이유가 없다. 이렇게
    해 둬야 다음 조율에서 같은 시간을 또 내놓지 않는다(취소된 회의는 막힌
    시간으로 안 세므로 이것이 유일한 기억이다).

    shortcut: "이 시간만 / 그날 종일" 선택은 없다. 목업과 프론트의 거절 창이
    한 줄 이유만 받는다. 날 전체를 막고 싶으면 거절할 때 scope를 더한다.
    """
    db.add(
        ScheduleItem(
            user_id=decliner_id,
            source=ScheduleSource.MANUAL,
            kind=ScheduleKind.APPOINTMENT,
            title=None,
            recurrence=Recurrence.ONCE,
            start_at=meeting.start_at,
            end_at=meeting.end_at,
        )
    )
    meeting.status = MeetingStatus.CANCELLED
    db.add(meeting)

    scheduling.status = SchedulingStatus.RUNNING
    scheduling.closed_at = None
    db.add(scheduling)
