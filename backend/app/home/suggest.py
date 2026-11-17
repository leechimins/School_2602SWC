"""에이전트가 먼저 "회의 잡을까요?"를 꺼낸다. 팀장 홈의 카드 한 장.

사람이 버튼을 눌러야만 움직이면 도구지 에이전트가 아니다. 여기서 팀의 상태를
보고 **회의가 필요한 이유**가 생겼을 때만 제안한다. 이유가 곧 주제가 된다.

우선순위(먼저 맞는 하나만):
  1. 막힌 일      task.state = blocked
  2. 기한 지난 일  minutes.tasks.is_late — 늦음 알림과 같은 기준
  3. 마감 임박     room.due_date까지 14일 이하
  4. 회의 간격     마지막 회의(없으면 방 시작일)부터 7일 넘음

**제안만 한다.** 회의를 만들거나 바꾸지 않는다. 시작은 팀장이 누른다.
**규칙으로 정한다.** 왜 지금인지 한 줄로 설명할 수 있어야 한다(why.py와 같은 원칙).
**DB에 아무것도 안 쓴다.** 홈을 열 때 계산한다. "나중에"는 브라우저가 기억한다.

조용히 있을 때: 조율이 도는 중이거나, 7일 안에 잡힌 회의(확정 대기 포함)가
있거나, 마감이 지났으면 제안하지 않는다. 이미 만날 약속이 있으면 거기서 다룬다.

레인 B의 task를 **읽기만** 한다(홈이 이미 그렇게 한다).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlmodel import Session, col, func, select

from app.home.schemas import Suggestion
from app.meeting.models import Meeting, Scheduling
from app.minutes.models import Task
from app.minutes.tasks import is_late, live_tasks
from app.shared.enums import MeetingStatus, SchedulingStatus, TaskState
from app.shared.models import Room

DEADLINE_DAYS = 14  # 마감이 이만큼 남으면 준비 회의를 권한다
GAP_DAYS = 7  # 회의 사이가 이보다 벌어지면 권한다(한 학기 매주 회의를 가정한 실험과 같다)
QUIET_DAYS = 7  # 이 안에 잡힌 회의가 있으면 조용히 있는다


def suggest(db: Session, room: Room, now: datetime) -> Suggestion | None:
    today = now.date()
    # 마감 당일부터는 조용하다. 기간이 내일부터라 마감 안에 열 수 있는 날이 없다
    if room.due_date <= today or _busy(db, room.id, now):  # type: ignore[arg-type]
        return None
    tomorrow = today + timedelta(days=1)

    tasks = [t for t in db.exec(live_tasks(room.id)).all() if t.state != TaskState.DONE]  # type: ignore[arg-type]
    blocked = sorted((t for t in tasks if t.state == TaskState.BLOCKED), key=_due_first)
    if blocked:
        first = blocked[0].title
        more = f" 외 {len(blocked) - 1}개" if len(blocked) > 1 else ""
        return _card(
            room, "blocked", tomorrow, 3,
            # 제목 끝 받침에 따라 이/가가 갈려서 조사를 붙이지 않는다
            f"막힌 일이 있어요: ‘{first}’{more}. 같이 풀 회의가 필요해 보여요.",
            f"{first} 같이 풀기",
        )

    late = [t for t in tasks if is_late(t, today)]
    if late:
        return _card(
            room, "late", tomorrow, 3,
            f"기한이 지난 할 일이 {len(late)}개 있어요. 일정을 다시 맞춰 볼까요?",
            "기한 지난 할 일 다시 맞추기",
        )

    left = (room.due_date - today).days
    if 1 <= left <= DEADLINE_DAYS:
        return _card(
            room, "deadline", tomorrow, 7,
            f"마감까지 {left}일 남았어요. 그 전에 함께 점검해요.",
            f"{room.eval_method} 준비" if room.eval_method else "마감 준비",
        )

    last = db.exec(
        select(func.max(Meeting.start_at)).where(
            Meeting.room_id == room.id,
            col(Meeting.status).in_([MeetingStatus.CONFIRMED, MeetingStatus.DONE]),
            Meeting.start_at < now,
        )
    ).one()
    since = (today - (last.date() if last else room.start_date)).days
    if since > GAP_DAYS:
        reason = (
            f"지난 회의 후 {since}일 지났어요. 한번 모여 볼까요?"
            if last
            else f"팀을 만든 지 {since}일인데 아직 함께 만난 적이 없어요."
        )
        return _card(room, "gap", tomorrow, 5, reason, "정기 회의" if last else "첫 회의")
    return None


def _busy(db: Session, room_id: int, now: datetime) -> bool:
    running = db.exec(
        select(Scheduling.id).where(
            Scheduling.room_id == room_id, Scheduling.status == SchedulingStatus.RUNNING
        )
    ).first()
    booked = db.exec(
        select(Meeting.id).where(
            Meeting.room_id == room_id,
            col(Meeting.status).in_([MeetingStatus.PROPOSED, MeetingStatus.CONFIRMED]),
            Meeting.end_at >= now,
            Meeting.start_at <= now + timedelta(days=QUIET_DAYS),
        )
    ).first()
    return running is not None or booked is not None


def _due_first(task: Task) -> tuple[date, int]:
    return (task.due_date or date.max, task.id or 0)


def _card(room: Room, kind: str, start: date, days: int, reason: str, topic: str) -> Suggestion:
    """기간은 내일부터 days일. 마감을 넘기지 않는다."""
    end = min(start + timedelta(days=days - 1), max(room.due_date, start))
    return Suggestion(
        kind=kind,  # type: ignore[arg-type]
        reason=reason,
        topic=topic[:100],
        window_start=start,
        window_end=end,
    )
