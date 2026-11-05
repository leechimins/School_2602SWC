"""할 일 계산 — 늦음 판정, 목록 정렬, 사람별 개수, 알림.

AI를 쓰지 않는다. "지금"은 전부 시연 시계에서 읽는다 — 시계를 옮기면
늦음 뱃지와 늦음 알림이 같이 움직여야 한다.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlmodel import Session, col, select

from app.meeting.models import Meeting
from app.minutes.models import Task
from app.minutes.schemas import TaskCountOut, TaskOut, TaskSourceOut
from app.shared import demo_clock
from app.shared.base import KST
from app.shared.enums import NotificationKind, TaskState
from app.shared.models import Membership, User
from app.shared.notify import emit


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


# ── 알림 ────────────────────────────────────────────────────────────


def emit_late(db: Session, room_id: int) -> int:
    """늦은 할 일마다 늦음 알림을 낸다. 새로 생긴 장수를 돌려준다.

    여러 번 불러도 된다. 중복 방지 키에 기한을 넣어서 같은 할 일·같은
    기한이면 한 번만 뜨고, 기한이 바뀌면 다시 뜬다.

    받는 사람은 담당자. 담당자가 없으면 방 팀원 전원 — 누구 일도 아닌 채로
    늦어지는 게 팀이 가장 놓치기 쉬운 경우다.

    커밋하지 않는다. 부르는 쪽이 자기 트랜잭션에서 커밋한다.
    """
    on = today(db)
    late = [t for t in db.exec(live_tasks(room_id)).all() if is_late(t, on)]
    if not late:
        return 0
    everyone = [u.id for u in members(db, room_id)]

    created = 0
    for task in late:
        assert task.due_date is not None
        created += emit(
            db,
            room_id=room_id,
            user_ids=[task.assignee_user_id] if task.assignee_user_id else everyone,
            kind=NotificationKind.LATE,
            reason=f"'{task.title}' 기한({task.due_date.month}/{task.due_date.day})이 지났습니다.",
            dedupe=f"task{task.id}:due{task.due_date:%Y%m%d}",
            task_id=task.id,
        )
    return created


def emit_status(db: Session, task: Task, actor: User, at: datetime) -> int:
    """막힘·완료로 바뀌었을 때 나머지 팀원에게 알린다. 다른 상태면 0.

    바꾼 사람 본인에게는 보내지 않는다. 중복 방지 키에 바뀐 시각을 넣어
    막혔다가 풀렸다가 다시 막히면 다시 알린다.
    """
    if task.state == TaskState.BLOCKED:
        kind = NotificationKind.BLOCKED
        # 조사를 제목 받침에 맞추지 않아도 되는 문장으로 쓴다 ("에", "할 일을")
        reason = f"{actor.name}님이 '{task.title}'에서 막혔다고 표시했습니다."
    elif task.state == TaskState.DONE:
        kind = NotificationKind.DONE
        reason = f"{actor.name}님이 '{task.title}' 할 일을 완료했습니다."
    else:
        return 0

    others = [u.id for u in members(db, task.room_id) if u.id != actor.id]
    return emit(
        db,
        room_id=task.room_id,
        user_ids=others,
        kind=kind,
        reason=reason,
        dedupe=f"task{task.id}:at{at:%Y%m%d%H%M%S%f}",
        task_id=task.id,
    )
