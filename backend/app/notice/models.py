"""Notice 도메인 — 알림 · 에이전트 기록 · 웹 푸시. 레인 A.

알림 카드는 3종(늦음·막힘·완료)에 회의 관련 셋이 더 붙는다. 앞의 둘은
챙기라는 알림이고 "완료"만 좋은 소식이라, 뱃지가 둘을 구분해야 한다.

늦음·막힘·완료는 할 일에서 나오는데 할 일은 B 것이다. 그래서 B가
notification 테이블에 직접 쓰지 않고, A가 내놓는 emit() 함수를 부른다.
명세가 "카드는 B가 만듦"이라고 적은 것이 이 뜻이다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.shared.base import enum_text, in_check, ts
from app.shared.enums import NotificationKind


class Notification(SQLModel, table=True):
    """알림 카드 한 장."""

    __tablename__ = "notification"
    __table_args__ = (
        # 같은 카드는 상황이 바뀔 때만 다시 뜬다. dedupe_key에 상황을 녹여
        # 넣으므로(예: late:task42:due20261120) 알림함이 같은 카드로 차지 않는다.
        UniqueConstraint("user_id", "dedupe_key", name="uq_notification_dedupe"),
        CheckConstraint(in_check("kind", NotificationKind), name="ck_notice_kind"),
    )

    id: int | None = Field(default=None, primary_key=True)
    room_id: int = Field(foreign_key="room.id", ondelete="CASCADE", index=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)

    kind: NotificationKind = enum_text(length=20)

    task_id: int | None = Field(
        default=None, foreign_key="task.id", ondelete="CASCADE", index=True
    )
    meeting_id: int | None = Field(
        default=None, foreign_key="meeting.id", ondelete="CASCADE"
    )

    reason: str = Field(max_length=200)  # 이유 한 줄
    dedupe_key: str = Field(max_length=100)

    read_at: datetime | None = ts(nullable=True)
    created_at: datetime = ts(auto_now=True, index=True)


class AgentLog(SQLModel, table=True):
    """에이전트가 한 일 기록. 무엇을, 왜, 언제.

    읽음 처리 없이 쌓인다. 알림 화면에서 따로 보여 준다 — 브리프의
    "에이전트가 한 일 기록(무엇을, 왜)"이다.
    """

    __tablename__ = "agent_log"

    id: int | None = Field(default=None, primary_key=True)
    room_id: int = Field(foreign_key="room.id", ondelete="CASCADE", index=True)
    # 특정 사람과 상관없는 일(판단 에이전트가 한 일)이면 비운다.
    user_id: int | None = Field(
        default=None, foreign_key="user.id", ondelete="CASCADE"
    )

    what: str = Field(max_length=200)
    why: str = Field(max_length=300)

    created_at: datetime = ts(auto_now=True, index=True)


class PushSubscription(SQLModel, table=True):
    """웹 푸시 구독.

    권한을 거부하면 행이 안 생기고 "앱 안에서만 알려 드려요"로 간다.
    웹 푸시는 밀렸을 때 팀 전체에서 제일 먼저 빼는 것이라, 없어도 알림함은
    그대로 돌아가야 한다.
    """

    __tablename__ = "push_subscription"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)

    endpoint: str = Field(max_length=500, unique=True)
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)

    created_at: datetime = ts(auto_now=True)
