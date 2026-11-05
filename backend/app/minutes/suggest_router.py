"""Suggest — 확정 전 AI 제안 확정·고치기·버리기. 레인 B.

제안은 task 중 confirmed=false인 행이다. 버린 제안은 dropped=true로 남는다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session, col, select

from app.minutes import tasks as task_calc
from app.minutes.common import apply_patch
from app.minutes.models import Task
from app.minutes.record import suggestion_out
from app.minutes.schemas import (
    ConfirmIn,
    ConfirmOut,
    SuggestionOut,
    SuggestionPatch,
)
from app.shared import demo_clock
from app.shared.auth import current_user_id, require_member
from app.shared.db import session_dep

router = APIRouter(prefix="/rooms/{room_id}", tags=["suggest"])


_ALREADY_CONFIRMED = {
    "code": "ALREADY_CONFIRMED",
    "message": "이미 확정된 할 일입니다.",
}


def _suggestion_not_found() -> HTTPException:
    return HTTPException(
        status.HTTP_404_NOT_FOUND,
        detail={"code": "NOT_FOUND", "message": "그 제안이 없습니다."},
    )


def _suggestion(db: Session, room_id: int, suggestion_id: int) -> Task:
    """이 방의 버리지 않은 제안 하나. 확정 여부는 부르는 쪽이 본다."""
    task = db.exec(
        select(Task)
        .where(
            Task.id == suggestion_id,
            Task.room_id == room_id,
            col(Task.dropped).is_(False),
        )
        .with_for_update()
    ).first()
    if task is None:
        raise _suggestion_not_found()
    return task



@router.post(
    "/suggestions/confirm", response_model=ConfirmOut, summary="제안 확정하기"
)
def confirm_suggestions(
    room_id: int,
    body: ConfirmIn,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> ConfirmOut:
    """AI 제안을 할 일로 확정합니다. 여러 개를 한꺼번에 보낼 수 있습니다.

    - 담당자가 비어 있어도 확정됩니다 ("담당자 없음"으로 들어감).
    - 확정한 사람과 시각이 남습니다. 시각은 시연 시계 기준입니다.
    - 하나라도 이미 확정됐으면 409 `ALREADY_CONFIRMED`이고 아무것도 확정하지 않습니다.
    - 없거나 버렸거나 다른 방의 제안이 섞이면 404 `NOT_FOUND`.
    """
    require_member(db, room_id, user_id)
    ids = list(dict.fromkeys(body.suggestion_ids))

    # 두 사람이 같은 제안을 동시에 누를 수 있다. 행을 잠가서 뒤에 온 쪽이
    # 앞쪽 확정을 본 뒤 409를 받게 한다.
    tasks = db.exec(
        select(Task)
        .where(
            col(Task.id).in_(ids),
            Task.room_id == room_id,
            col(Task.dropped).is_(False),
        )
        .with_for_update()
    ).all()
    if len(tasks) != len(ids):
        raise _suggestion_not_found()
    if any(task.confirmed for task in tasks):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_ALREADY_CONFIRMED)

    now = demo_clock.now(db)
    for task in tasks:
        task.confirmed = True
        task.confirmed_by = user_id
        task.confirmed_at = now
        db.add(task)
    db.commit()
    by_id = {task.id: task for task in tasks}
    return ConfirmOut(
        tasks=task_calc.task_outs(db, [by_id[i] for i in sorted(ids)], user_id)
    )


@router.patch(
    "/suggestions/{suggestion_id}", response_model=SuggestionOut, summary="제안 고치기"
)
def edit_suggestion(
    room_id: int,
    suggestion_id: int,
    body: SuggestionPatch,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> SuggestionOut:
    """확정 전 제안의 제목·담당자·기한을 고칩니다. 보낸 칸만 바뀝니다.

    - 담당자·기한은 null을 보내면 비웁니다. 제목은 비울 수 없습니다.
    - 담당자는 이 방 팀원만 됩니다.
    - 이미 확정된 할 일이면 409 `ALREADY_CONFIRMED` (할 일 고치기를 쓰세요).
    """
    require_member(db, room_id, user_id)
    task = _suggestion(db, room_id, suggestion_id)
    if task.confirmed:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_ALREADY_CONFIRMED)

    apply_patch(db, room_id, task, body)
    db.add(task)
    db.commit()
    db.refresh(task)
    return suggestion_out(task, task_calc.user_names(db, {task.assignee_user_id}))


@router.delete(
    "/suggestions/{suggestion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="제안 버리기",
)
def drop_suggestion(
    room_id: int,
    suggestion_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> Response:
    """확정 전 제안을 버립니다. 되돌릴 수 없으므로 화면에서 한 번 더 묻습니다.

    - 행을 지우지 않고 "필요 없음"(`dropped`)으로 둡니다. 회의록에서 빠집니다.
    - 이미 확정된 할 일이면 409 `ALREADY_CONFIRMED` (할 일의 "필요 없음"을 쓰세요).
    """
    require_member(db, room_id, user_id)
    task = _suggestion(db, room_id, suggestion_id)
    if task.confirmed:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_ALREADY_CONFIRMED)

    task.dropped = True
    db.add(task)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
