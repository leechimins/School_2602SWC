"""Record · Suggest · Task · 외부 연동 — 회의록에서 할 일까지. 레인 B.

회의록은 meeting 행(A가 confirmed까지 씀)에 붙는다. 받아적은 글이
transcript_segment로 쌓이고, 요약하면 minutes + minutes_item이 생기고,
뽑힌 할 일은 task에 confirmed=false로 들어간다. 사람이 확정해야
confirmed=true가 되어 할 일 목록에 보인다.

"제안"과 "할 일"은 별도 테이블이 아니라 task의 confirmed 값이다
(db-설계.md §0 "두 가지 이름, 한 행").
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.shared.base import enum_text, in_check, ts
from app.shared.enums import (
    CalendarKind,
    LinkStatus,
    MinutesItemKind,
    MinutesStatus,
    TaskOrigin,
    TaskState,
)


class CalendarLink(SQLModel, table=True):
    """연동 상태. 내 조건 화면이 연결 여부와 마지막 동기화 시각을 여기서 읽는다.

    연동은 전부 선택이다. 이 행이 없어도, status가 failed여도 직접 입력으로
    모든 화면이 돈다. 사람당 종류별로 하나만 둔다 — 명세의 연결·끊기 경로가
    종류 단위(/me/integrations/everytime)이기 때문이다.
    """

    __tablename__ = "calendar_link"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", name="uq_calendar_link_user_kind"),
        CheckConstraint(in_check("kind", CalendarKind), name="ck_calendar_link_kind"),
        CheckConstraint(
            in_check("status", LinkStatus), name="ck_calendar_link_status"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    kind: CalendarKind = enum_text(length=10)
    # 에브리타임 아이디, 또는 구글 계정.
    external_ref: str = Field(max_length=200)
    # 구글만 쓴다. 에브리타임은 공유 링크 하나라 토큰이 없다.
    access_token: str | None = Field(default=None, max_length=2000)
    refresh_token: str | None = Field(default=None, max_length=2000)
    status: LinkStatus = enum_text(length=10)
    last_synced_at: datetime | None = ts(nullable=True)
    created_at: datetime = ts(auto_now=True)


class TranscriptSegment(SQLModel, table=True):
    """받아적은 글 한 토막. 음성은 저장하지 않고 글자만 남긴다.

    (meeting_id, seq)가 유일하다. 받아적기가 끊겼다 다시 올라와도
    같은 seq는 한 번만 들어가므로 중복·누락을 서버가 가려낼 수 있다.

    speaker_label은 STT가 붙이는 익명 라벨("A", "B")이고 제안일 뿐이다.
    speaker_user_id는 사람이 라벨을 이름에 매핑하거나 줄마다 직접 고를 때
    채운다. 둘 다 비어 있어도, 라벨만 있어도 정상이다.
    """

    __tablename__ = "transcript_segment"
    __table_args__ = (
        UniqueConstraint("meeting_id", "seq", name="uq_segment_meeting_seq"),
        CheckConstraint("seq >= 0", name="ck_segment_seq"),
    )

    id: int | None = Field(default=None, primary_key=True)
    meeting_id: int = Field(foreign_key="meeting.id", ondelete="CASCADE", index=True)
    seq: int
    speaker_label: str | None = Field(default=None, max_length=8)
    speaker_user_id: int | None = Field(
        default=None, foreign_key="user.id", ondelete="SET NULL"
    )
    text: str
    created_at: datetime = ts(auto_now=True)


class Minutes(SQLModel, table=True):
    """회의록 한 건. 회의 하나에 하나."""

    __tablename__ = "minutes"
    __table_args__ = (
        CheckConstraint(in_check("status", MinutesStatus), name="ck_minutes_status"),
    )

    id: int | None = Field(default=None, primary_key=True)
    meeting_id: int = Field(
        foreign_key="meeting.id", ondelete="CASCADE", unique=True, index=True
    )
    # 주제 한 줄. 날짜별 목록에도 이게 보여서 나중에 찾는다.
    headline: str = Field(max_length=100)
    status: MinutesStatus = enum_text(length=12)
    created_at: datetime = ts(auto_now=True)


class MinutesItem(SQLModel, table=True):
    """요약 항목 하나. 결정 / 논의 / 보류.

    원문의 해당 발화로 점프하지 않기로 해서 transcript_segment를 가리키는
    열이 없다.
    """

    __tablename__ = "minutes_item"
    __table_args__ = (
        CheckConstraint(in_check("kind", MinutesItemKind), name="ck_item_kind"),
    )

    id: int | None = Field(default=None, primary_key=True)
    minutes_id: int = Field(foreign_key="minutes.id", ondelete="CASCADE", index=True)
    kind: MinutesItemKind = enum_text(length=12)
    seq: int
    text: str


class Task(SQLModel, table=True):
    """할 일. confirmed=false인 행이 곧 회의록의 "할 일 제안"이다.

    확정 전 제안은 할 일 목록과 내 할 일에 넣지 않는다. 담당자는 비어
    있는 게 정상이다. 진행률 숫자·예상 소요 시간은 열이 없다.

    "필요 없음"은 행을 지우지 않고 dropped=true로 둔다("삭제"라고 쓰지 않음).
    """

    __tablename__ = "task"
    __table_args__ = (
        CheckConstraint(in_check("state", TaskState), name="ck_task_state"),
        CheckConstraint(in_check("origin", TaskOrigin), name="ck_task_origin"),
        # 확정된 할 일에만 확정 시각이 있고, 확정한 사람은 확정 시각이 있을 때만 있다.
        CheckConstraint(
            "(confirmed AND confirmed_at IS NOT NULL) "
            "OR (NOT confirmed AND confirmed_at IS NULL AND confirmed_by IS NULL)",
            name="ck_task_confirmed",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    room_id: int = Field(foreign_key="room.id", ondelete="CASCADE", index=True)
    # 출처 회의. 직접 추가면 비운다.
    meeting_id: int | None = Field(
        default=None, foreign_key="meeting.id", ondelete="SET NULL", index=True
    )
    title: str = Field(max_length=200)
    due_date: date | None = Field(default=None)
    assignee_user_id: int | None = Field(
        default=None, foreign_key="user.id", ondelete="SET NULL", index=True
    )
    state: TaskState = enum_text(length=10)
    origin: TaskOrigin = enum_text(length=10)
    confirmed: bool = Field(default=False)
    confirmed_by: int | None = Field(
        default=None, foreign_key="user.id", ondelete="SET NULL"
    )
    confirmed_at: datetime | None = ts(nullable=True)
    dropped: bool = Field(default=False)
    created_at: datetime = ts(auto_now=True)
