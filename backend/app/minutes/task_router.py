"""Task — 확정된 할 일. 레인 B.

할 일은 task 중 confirmed=true이고 dropped=false인 행이다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlmodel import Session, col, func, select

from app.minutes import tasks as task_calc
from app.minutes.common import apply_patch, require_room_member_id
from app.minutes.models import Task
from app.minutes.schemas import (
    MyTaskListOut,
    ReassignIn,
    StatusIn,
    TaskCreateIn,
    TaskListOut,
    TaskOut,
    TaskPatch,
)
from app.shared import demo_clock
from app.shared.auth import current_user_id, require_member
from app.shared.db import session_dep
from app.shared.enums import TaskOrigin, TaskState
from app.shared.models import User

router = APIRouter(prefix="/rooms/{room_id}", tags=["task"])


def _task(db: Session, room_id: int, task_id: int, *, lock: bool = True) -> Task:
    """이 방의 확정된 할 일 하나. 제안이나 필요 없음은 404.

    상태·내용을 바꾸는 요청은 행을 잠근다. 폰 화면 둘에서 같은 할 일을
    동시에 바꿀 수 있다. 읽기만 하는 하나 보기는 `lock=False`.
    """
    query = task_calc.live_tasks(room_id).where(Task.id == task_id)
    if lock:
        query = query.with_for_update()
    task = db.exec(query).first()
    if task is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "그 할 일이 없습니다."},
        )
    return task


def _task_out(db: Session, task: Task, viewer_id: int) -> TaskOut:
    return task_calc.task_outs(db, [task], viewer_id)[0]


@router.get("/tasks", response_model=TaskListOut, summary="팀 할 일 보기")
def list_tasks(
    room_id: int,
    state: TaskState | None = Query(default=None, description="이 상태만"),
    assignee_user_id: int | None = Query(default=None, description="이 사람이 담당인 것만"),
    unassigned: bool = Query(default=False, description="true면 담당자 없음만"),
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> TaskListOut:
    """확정된 할 일만. 담당자 없음 → 나 → 다른 사람 순이고 묶음 안은 기한 순입니다.

    - 확정 전 AI 제안은 나오지 않습니다. 대신 `suggestion_count`로 수를 줍니다.
    - "필요 없음"으로 뺀 할 일은 나오지 않습니다.
    - 부를 때 늦음 판정도 돌려서 늦은 할 일에 늦음 알림을 냅니다 (같은 건은 한 번만).
    """
    require_member(db, room_id, user_id)
    task_calc.emit_late(db, room_id)
    db.commit()

    query = task_calc.live_tasks(room_id)
    if state is not None:
        query = query.where(Task.state == state)
    if unassigned:
        query = query.where(col(Task.assignee_user_id).is_(None))
    elif assignee_user_id is not None:
        query = query.where(Task.assignee_user_id == assignee_user_id)
    tasks = task_calc.team_order(list(db.exec(query).all()), user_id)

    suggestion_count = db.exec(
        select(func.count())
        .select_from(Task)
        .where(
            Task.room_id == room_id,
            col(Task.confirmed).is_(False),
            col(Task.dropped).is_(False),
        )
    ).one()
    return TaskListOut(
        tasks=task_calc.task_outs(db, tasks, user_id),
        task_counts=task_calc.task_counts(db, room_id),
        suggestion_count=suggestion_count,
    )


@router.get("/tasks/mine", response_model=MyTaskListOut, summary="내 할 일 보기")
def list_my_tasks(
    room_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> MyTaskListOut:
    """내가 담당인 확정된 할 일. 기한 순이고 기한이 없으면 맨 뒤입니다."""
    require_member(db, room_id, user_id)
    task_calc.emit_late(db, room_id)
    db.commit()

    tasks = db.exec(
        task_calc.live_tasks(room_id).where(Task.assignee_user_id == user_id)
    ).all()
    return MyTaskListOut(
        tasks=task_calc.task_outs(db, task_calc.mine_order(list(tasks)), user_id)
    )


@router.post(
    "/tasks",
    response_model=TaskOut,
    status_code=status.HTTP_201_CREATED,
    summary="할 일 직접 추가",
)
def create_task(
    room_id: int,
    body: TaskCreateIn,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> TaskOut:
    """AI 없이 할 일을 바로 만듭니다. 만든 사람이 확정한 사람으로 바로 확정됩니다.

    - 출처 회의가 없어 `source`가 null입니다.
    - 담당자는 이 방 팀원만, 비워도 됩니다.
    """
    require_member(db, room_id, user_id)
    if body.assignee_user_id is not None:
        require_room_member_id(db, room_id, body.assignee_user_id)

    now = demo_clock.now(db)
    task = Task(
        room_id=room_id,
        title=body.title,
        due_date=body.due_date,
        assignee_user_id=body.assignee_user_id,
        state=TaskState.TODO,
        origin=TaskOrigin.MANUAL,
        confirmed=True,
        confirmed_by=user_id,
        confirmed_at=now,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return _task_out(db, task, user_id)


@router.get("/tasks/{task_id}", response_model=TaskOut, summary="할 일 하나 보기")
def get_task(
    room_id: int,
    task_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> TaskOut:
    """고치기 화면용. 확정 전 제안이나 필요 없음으로 뺀 할 일이면 404."""
    require_member(db, room_id, user_id)
    return _task_out(db, _task(db, room_id, task_id, lock=False), user_id)


@router.patch(
    "/tasks/{task_id}/status", response_model=TaskOut, summary="할 일 상태 바꾸기"
)
def change_status(
    room_id: int,
    task_id: int,
    body: StatusIn,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> TaskOut:
    """시작 전 · 진행 중 · 막힘 · 완료 사이를 어느 방향으로든 바꿉니다.

    - 담당자만 바꿀 수 있습니다. 아니면 403 `NOT_ASSIGNEE`. 담당자가 없는 할 일은 전원.
    - 막힘·완료로 바뀌면 나머지 팀원에게 알림이 갑니다.
    - 지금과 같은 상태를 보내면 아무 일도 일어나지 않습니다.
    """
    require_member(db, room_id, user_id)
    task = _task(db, room_id, task_id)
    if not task_calc.can_change_status(task, user_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "NOT_ASSIGNEE",
                "message": "담당자만 상태를 바꿀 수 있습니다.",
            },
        )

    if task.state != body.state:
        task.state = body.state
        db.add(task)
        actor = db.get(User, user_id)
        assert actor is not None
        task_calc.emit_status(db, task, actor)
        db.commit()
        db.refresh(task)
    return _task_out(db, task, user_id)


@router.patch("/tasks/{task_id}", response_model=TaskOut, summary="할 일 내용 고치기")
def edit_task(
    room_id: int,
    task_id: int,
    body: TaskPatch,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> TaskOut:
    """제목·담당자·기한을 고칩니다. 팀원 누구나 됩니다. 보낸 칸만 바뀝니다.

    - 담당자·기한은 null을 보내면 비웁니다. 제목은 비울 수 없습니다.
    - 담당자는 이 방 팀원만 됩니다.
    """
    require_member(db, room_id, user_id)
    task = _task(db, room_id, task_id)
    apply_patch(db, room_id, task, body)
    db.add(task)
    db.commit()
    db.refresh(task)
    return _task_out(db, task, user_id)


@router.post(
    "/tasks/{task_id}/reassign", response_model=TaskOut, summary="담당자 넘기기"
)
def reassign_task(
    room_id: int,
    task_id: int,
    body: ReassignIn,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> TaskOut:
    """담당자만 바꿉니다. null이면 담당자 없음. 내용 고치기와 같은 규칙입니다."""
    require_member(db, room_id, user_id)
    task = _task(db, room_id, task_id)
    apply_patch(db, room_id, task, TaskPatch(assignee_user_id=body.assignee_user_id))
    db.add(task)
    db.commit()
    db.refresh(task)
    return _task_out(db, task, user_id)


@router.post(
    "/tasks/{task_id}/dismiss",
    status_code=status.HTTP_204_NO_CONTENT,
    summary='할 일 빼기 ("필요 없음")',
)
def dismiss_task(
    room_id: int,
    task_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> Response:
    """할 일을 "필요 없음"으로 뺍니다. 되돌릴 수 없으므로 화면에서 한 번 더 묻습니다.

    - 팀원 누구나 됩니다. 행을 지우지 않고 목록에서만 빠집니다.
    """
    require_member(db, room_id, user_id)
    task = _task(db, room_id, task_id)
    task.dropped = True
    db.add(task)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
