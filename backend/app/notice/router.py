"""알림 — 홈 오른쪽 위 종에서 열리는 목록.

읽는 쪽만 있다. 만드는 쪽은 `shared/notify.py`의 emit()이고, 부르는 자리는
할 일(B)과 조율(A)에 흩어져 있다.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlmodel import Session, SQLModel, col, func, select

from app.notice.models import Notification
from app.shared.auth import current_user_id, require_member
from app.shared.db import session_dep
from app.shared.demo_clock import now as clock_now
from app.shared.enums import NotificationKind

router = APIRouter(prefix="/rooms/{room_id}/notifications", tags=["notice"])


class NotificationOut(SQLModel):
    """알림 카드 한 장. 브리프가 정한 내용이 그대로 들어간다 —
    종류 뱃지(kind), 이유 한 줄(reason), 관련 할 일(task_id), 이동 버튼의 대상.
    """

    id: int
    kind: NotificationKind
    reason: str
    task_id: int | None = None
    meeting_id: int | None = None
    read_at: datetime | None = None
    created_at: datetime


class NotificationListOut(SQLModel):
    """목록은 객체로 감싼다(명세 권장 규칙 5). 종의 숫자가 여기서 나온다."""

    items: list[NotificationOut]
    unread_count: int


class ReadIn(SQLModel):
    """ids를 안 보내면 모두 읽음이다. 명세의 "모두 / 개별"."""

    ids: list[int] | None = None


class ReadOut(SQLModel):
    unread_count: int


def _unread(db: Session, room_id: int, user_id: int) -> int:
    return db.exec(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.room_id == room_id,
            Notification.user_id == user_id,
            col(Notification.read_at).is_(None),
        )
    ).one()


@router.get("", response_model=NotificationListOut)
def list_notifications(
    room_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> NotificationListOut:
    """내 알림만. 최신순.

    읽은 것도 같이 준다 — 브리프가 "알림이 없다"는 빈 화면에 "좋은 상태라고
    쓴다"로 정했고, 읽은 카드를 숨기면 방금 읽은 것이 사라져 그게 오류처럼
    보인다.
    """
    require_member(db, room_id, user_id)
    rows = db.exec(
        select(Notification)
        .where(Notification.room_id == room_id, Notification.user_id == user_id)
        .order_by(col(Notification.created_at).desc(), col(Notification.id).desc())
    ).all()
    return NotificationListOut(
        items=[NotificationOut.model_validate(r, from_attributes=True) for r in rows],
        unread_count=sum(1 for r in rows if r.read_at is None),
    )


@router.post("/read", response_model=ReadOut)
def mark_read(
    room_id: int,
    body: ReadIn,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> ReadOut:
    """읽음 표시. 남의 알림은 ids에 넣어도 안 바뀐다.

    이미 읽은 것은 건드리지 않는다 — 다시 찍으면 "언제 읽었나"가 뒤로 밀린다.
    """
    require_member(db, room_id, user_id)
    statement = select(Notification).where(
        Notification.room_id == room_id,
        Notification.user_id == user_id,
        col(Notification.read_at).is_(None),
    )
    if body.ids is not None:
        statement = statement.where(col(Notification.id).in_(body.ids))

    stamp = clock_now(db)
    for notification in db.exec(statement).all():
        notification.read_at = stamp
        db.add(notification)
    db.commit()

    return ReadOut(unread_count=_unread(db, room_id, user_id))
