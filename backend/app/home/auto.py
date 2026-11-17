"""맡겨 두면 에이전트가 조율까지 스스로 시작한다.

회의 제안(suggest.py)은 이유를 찾아 팀장에게 보여 주기만 한다. 팀장이
"알아서 조율까지 해 줘"를 켜 두면(agent_setting.auto_schedule) 같은 이유가
생겼을 때 팀장을 기다리지 않고 조율을 연다. 그 뒤는 사람이 누른 조율과
똑같다 — 대리인들이 협상하고, 회의안은 각자 수락해야 확정된다.

**언제 도나.** 팀원 누구든 홈을 열 때. 무료 서버라 정해진 시각에 깨워 줄
스케줄러가 없다. 팀원이 앱을 여는 순간이 곧 팀 상태를 다시 볼 순간이다.

**언제 안 도나.** 제안이 없을 때(조율 중·7일 안에 잡힌 회의·마감 지남이면
제안도 없다), 수락을 기다리는 회의가 있을 때, 오늘 이미 한 번 시작했을 때.

**규칙으로만 정한다.** 제안과 같은 이유 한 줄을 에이전트 기록에 남긴다.
"""

from __future__ import annotations

from datetime import datetime, time

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.home.suggest import suggest
from app.meeting import runner
from app.meeting.models import AgentSetting, Meeting
from app.meeting.schemas import SchedulingStartIn
from app.meeting.service import start_scheduling
from app.notice.agent_log import record
from app.shared.base import KST
from app.shared.enums import MeetingStatus, Mode, SchedulingStatus
from app.shared.models import Room

DURATION_MIN = 120  # 조율 시작 화면의 기본값과 같다
MODE = Mode.ANY


def auto_on(db: Session, room_id: int) -> bool:
    setting = db.get(AgentSetting, room_id)
    return setting is not None and setting.auto_schedule


def set_auto(db: Session, room_id: int, on: bool) -> None:
    setting = db.get(AgentSetting, room_id) or AgentSetting(room_id=room_id)
    setting.auto_schedule = on
    db.add(setting)
    db.commit()


def maybe_start(db: Session, room: Room, now: datetime) -> int | None:
    """조건이 맞으면 조율을 열고 그 id를 돌려준다. 아니면 None."""
    setting = db.get(AgentSetting, room.id)
    today = now.date()
    if setting is None or not setting.auto_schedule or setting.last_auto_on == today:
        return None
    card = suggest(db, room, now)
    if card is None or _awaiting(db, room.id, now):  # type: ignore[arg-type]
        return None

    setting.last_auto_on = today
    db.add(setting)
    record(db, room.id, f"{card.topic} 조율을 스스로 시작", card.reason)  # type: ignore[arg-type]
    body = SchedulingStartIn(
        topic=card.topic,
        window_start=datetime.combine(card.window_start, time(0, 0), KST),
        window_end=datetime.combine(card.window_end, time(23, 59), KST),
        duration_min=DURATION_MIN,
        mode=MODE,
    )
    try:
        # 팀장 이름으로 연다. 팀장이 못 오는 후보를 뒤로 미는 규칙이 그대로 선다.
        scheduling = start_scheduling(db, room.id, room.leader_user_id, body)  # type: ignore[arg-type]
    except IntegrityError:
        # 두 팀원이 같은 순간 홈을 열었다. 먼저 연 쪽이 이미 조율을 돌린다.
        db.rollback()
        return None

    assert scheduling.id is not None
    if scheduling.status == SchedulingStatus.RUNNING:
        runner.start(scheduling.id)
    else:
        record(db, room.id, f"{card.topic} 조율 멈춤", "그 기간에 모두 되는 시간이 없었어요")  # type: ignore[arg-type]
        db.commit()
    return scheduling.id


def _awaiting(db: Session, room_id: int, now: datetime) -> bool:
    """수락을 기다리는 회의가 있으면 새 조율을 열 수 없다(조율 시작 API와 같은 규칙)."""
    return (
        db.exec(
            select(Meeting.id).where(
                Meeting.room_id == room_id,
                Meeting.status == MeetingStatus.PROPOSED,
                Meeting.end_at >= now,
            )
        ).first()
        is not None
    )

