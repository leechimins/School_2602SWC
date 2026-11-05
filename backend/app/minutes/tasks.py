"""할 일 계산 — 늦음 판정, 목록 정렬, 사람별 개수.

AI를 쓰지 않는다. "지금"은 전부 시연 시계에서 읽는다 — 시계를 옮기면
늦음 뱃지가 같이 움직여야 한다.
"""

from __future__ import annotations

from datetime import date

from sqlmodel import Session, col, select

from app.meeting.models import Meeting
from app.minutes.models import Task
from app.minutes.schemas import TaskCountOut, TaskOut, TaskSourceOut
from app.shared import demo_clock
from app.shared.base import KST
from app.shared.enums import TaskState
from app.shared.models import Membership, User


def today(db: Session) -> date:
    return demo_clock.now(db).date()


def is_late(task: Task, on: date) -> bool:
    """늦음은 상태가 아니라 뱃지다. 상태와 섞지 않는다."""
    return (
        task.due_date is not None
        and task.due_date < on
        and task.state != TaskState.DONE
    )


def can_change_status(task: Task, viewer_id: int) -> bool:
    """담당자만. 담당자가 없으면 전원.

    담당자 없음이 회의 직후 가장 큰 묶음이라, 담당자만으로 막으면 아무도
    손을 못 댄다.
    """
    return task.assignee_user_id is None or task.assignee_user_id == viewer_id


def live_tasks(room_id: int):
    """확정됐고 필요 없음이 아닌 할 일. 할 일 목록이 보는 범위."""
    return select(Task).where(
        Task.room_id == room_id,
        col(Task.confirmed).is_(True),
        col(Task.dropped).is_(False),
    )


def members(db: Session, room_id: int) -> list[User]:
    return list(
        db.exec(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.room_id == room_id)
            .order_by(Membership.joined_at, Membership.id)
        ).all()
    )


def task_outs(db: Session, tasks: list[Task], viewer_id: int) -> list[TaskOut]:
    """이름과 출처 회의를 한 번에 읽어 붙인다. 할 일마다 따로 읽지 않는다."""
    on = today(db)
    user_ids = {t.assignee_user_id for t in tasks if t.assignee_user_id}
    names = (
        dict(db.exec(select(User.id, User.name).where(col(User.id).in_(user_ids))).all())
        if user_ids
        else {}
    )
    meeting_ids = {t.meeting_id for t in tasks if t.meeting_id}
    meetings = (
        {
            m.id: m
            for m in db.exec(select(Meeting).where(col(Meeting.id).in_(meeting_ids))).all()
        }
        if meeting_ids
        else {}
    )

    def source(task: Task) -> TaskSourceOut | None:
        meeting = meetings.get(task.meeting_id) if task.meeting_id else None
        if meeting is None:
            return None
        return TaskSourceOut(
            meeting_id=meeting.id,
            held_on=meeting.start_at.astimezone(KST).date(),
            topic=meeting.topic,
        )

    return [
        TaskOut(
            id=task.id,
            title=task.title,
            due_date=task.due_date,
            assignee_user_id=task.assignee_user_id,
            assignee_name=names.get(task.assignee_user_id),
            state=task.state,
            source=source(task),
            is_late=is_late(task, on),
            can_change_status=can_change_status(task, viewer_id),
            can_edit=True,
        )
        for task in tasks
    ]


def _due_key(task: Task) -> tuple:
    # 기한 없는 것은 맨 뒤
    return (task.due_date is None, task.due_date or date.max, task.id)


def team_order(tasks: list[Task], viewer_id: int) -> list[Task]:
    """담당자 없음 → 나 → 다른 사람. 다른 사람은 사람별로 모은다."""

    def key(task: Task) -> tuple:
        if task.assignee_user_id is None:
            group = (0, 0)
        elif task.assignee_user_id == viewer_id:
            group = (1, 0)
        else:
            group = (2, task.assignee_user_id)
        return (group, *_due_key(task))

    return sorted(tasks, key=key)


def mine_order(tasks: list[Task]) -> list[Task]:
    return sorted(tasks, key=_due_key)


def task_counts(db: Session, room_id: int) -> list[TaskCountOut]:
    """사람별 남은 할 일 수. 완료와 필요 없음은 빼고, 0인 사람도 넣는다."""
    remaining = [
        t
        for t in db.exec(live_tasks(room_id)).all()
        if t.state != TaskState.DONE and t.assignee_user_id is not None
    ]
    return [
        TaskCountOut(
            user_id=user.id,
            name=user.name,
            remaining=sum(t.assignee_user_id == user.id for t in remaining),
        )
        for user in members(db, room_id)
    ]

