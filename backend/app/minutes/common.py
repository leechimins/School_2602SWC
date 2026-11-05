"""Suggest와 Task가 같이 쓰는 규칙. 제안 고치기와 할 일 고치기는 같은 행(task)을 같은 규칙으로 바꾼다."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.minutes.models import Task
from app.minutes.schemas import SuggestionPatch, TaskPatch
from app.shared.models import Membership


def require_room_member_id(db: Session, room_id: int, user_id: int) -> None:
    """담당자로 고를 수 있는 사람인지. 이 방 팀원만 된다."""
    found = db.exec(
        select(Membership.id).where(
            Membership.room_id == room_id, Membership.user_id == user_id
        )
    ).first()
    if found is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_INPUT",
                "field": "assignee_user_id",
                "message": "이 방의 팀원만 담당자로 고를 수 있습니다.",
            },
        )


def apply_patch(
    db: Session, room_id: int, task: Task, body: SuggestionPatch | TaskPatch
) -> None:
    """제목·담당자·기한 중 보낸 칸만 바꾼다. 제안 고치기와 할 일 고치기가 같이 쓴다."""
    sent = body.model_fields_set
    if "title" in sent:
        if body.title is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_INPUT",
                    "field": "title",
                    "message": "제목은 비울 수 없습니다.",
                },
            )
        task.title = body.title
    if "assignee_user_id" in sent:
        if body.assignee_user_id is not None:
            require_room_member_id(db, room_id, body.assignee_user_id)
        task.assignee_user_id = body.assignee_user_id
    if "due_date" in sent:
        task.due_date = body.due_date
