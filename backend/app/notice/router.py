"""알림 — 홈 오른쪽 위 종에서 열리는 목록.

읽는 쪽만 있다. 만드는 쪽은 `shared/notify.py`의 emit()이고, 부르는 자리는
할 일(B)과 조율(A)에 흩어져 있다.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlmodel import Field, Session, SQLModel, col, func, select

from app.meeting.models import Meeting, YieldEntry
from app.notice.models import AgentLog, Notification
from app.shared.base import KST
from app.shared.models import User
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


# ── 에이전트가 한 일 · 양보 기록 ─────────────────────────────────────
# 알림 화면 아래 두 칸. 프론트 타입(frontend/src/types/notification.ts의
# ActivityLog)과 같은 모양이다. 주소가 /notifications 밑이 아니라서 라우터를 따로 둔다.

log_router = APIRouter(prefix="/rooms/{room_id}", tags=["notice"])

LOG_LIMIT = 50
"""각 칸에 내보내는 줄 수. 시연 한 번에 쌓이는 양보다 넉넉하다."""


class AgentLogOut(SQLModel):
    id: int = Field(description="기록 ID")
    at: datetime = Field(description="한 시각(시연 시계)")
    what: str = Field(description="무엇을 했나. 예: 발표 리허설 회의를 11월 16일(월) 15:00–17:00으로 제안했어요")
    why: str = Field(description="왜. 사람별 점수 숫자는 들어가지 않는다")


class YieldRecordOut(SQLModel):
    id: int = Field(description="양보 기록 ID")
    meeting_label: str = Field(description='"11월 4일 회의"처럼 어느 회의였나')
    user_id: int = Field(description="맞춰 준 사람")
    name: str = Field(description="맞춰 준 사람 이름")
    why: str = Field(description="얼마나 맞춰 줬나. 숫자 없이 조금/많이로만")


class ActivityOut(SQLModel):
    agent_log: list[AgentLogOut] = Field(description="에이전트가 한 일. 최신순")
    yield_records: list[YieldRecordOut] = Field(description="회의마다 누가 맞춰 줬나. 최신순")


def _양보말(discomfort: int) -> str:
    """양보의 크기를 숫자 없이. 경계는 scorer와 같다 — 4 이상이 "많이"."""
    return "많이 불편한 시간을 맞춰 줬어요" if discomfort >= 4 else "조금 불편한 시간을 맞춰 줬어요"


@log_router.get("/agent-log", response_model=ActivityOut)
def agent_log(
    room_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> ActivityOut:
    """에이전트가 한 일과 양보 기록. 읽음 처리 없이 쌓인다.

    yield_entry.reason은 그대로 내보내지 않는다. "내 불편 3/5만큼 맞춰 줘서 +1"처럼
    **점수 숫자가 들어 있는데** 이 화면은 방 전체가 본다(명세 권장 규칙 3).
    """
    require_member(db, room_id, user_id)

    logs = db.exec(
        select(AgentLog)
        .where(AgentLog.room_id == room_id)
        .order_by(col(AgentLog.created_at).desc(), col(AgentLog.id).desc())
        .limit(LOG_LIMIT)
    ).all()

    yields = db.exec(
        select(YieldEntry, Meeting.start_at, User.name)
        .join(Meeting, col(Meeting.id) == col(YieldEntry.meeting_id))
        .join(User, col(User.id) == col(YieldEntry.user_id))
        .where(YieldEntry.room_id == room_id)
        .order_by(col(YieldEntry.created_at).desc(), col(YieldEntry.id).desc())
        .limit(LOG_LIMIT)
    ).all()

    return ActivityOut(
        agent_log=[
            AgentLogOut(id=l.id, at=l.created_at, what=l.what, why=l.why)  # type: ignore[arg-type]
            for l in logs
        ],
        yield_records=[
            YieldRecordOut(
                id=y.id,  # type: ignore[arg-type]
                meeting_label=f"{start.astimezone(KST).month}월 {start.astimezone(KST).day}일 회의",
                user_id=y.user_id,
                name=name,
                why=_양보말(y.discomfort),
            )
            for y, start, name in yields
        ],
    )
