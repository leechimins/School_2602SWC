"""회의록 · 제안 · 할 일이 주고받는 모양. table=True가 없는 모델만 있다.

Field의 description은 Swagger에 그대로 보인다.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from sqlmodel import Field, SQLModel

from app.shared.enums import MeetingStatus, MinutesStatus, Mode, TaskState, TranscriptMode

# ── Record 입력 ─────────────────────────────────────────────────────


class RecordStartIn(SQLModel):
    """회의 기록 시작. 잡힌 회의에 붙이거나, 없으면 새로 만든다."""

    meeting_id: int | None = Field(
        default=None, description="기록을 붙일 확정된 회의. 비우면 회의를 새로 만든다"
    )
    topic: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="새로 만들 때 회의 주제. meeting_id가 없으면 필수",
    )
    mode: Literal[Mode.OFFLINE, Mode.ONLINE] = Field(
        default=Mode.OFFLINE, description="새로 만들 때 대면(offline)·비대면(online)"
    )


class TranscriptIn(SQLModel):
    """직접 쓰기. 원문 전체를 보내면 통째로 바꾼다."""

    text: str = Field(
        max_length=50_000,
        description="원문 전체. 줄마다 한 발언. `이름: 내용` 꼴이면 말한 사람으로 나눈다",
    )


# ── Record 출력 ─────────────────────────────────────────────────────


class PersonOut(SQLModel):
    user_id: int = Field(description="사용자 ID")
    name: str = Field(description="이름")


class TranscriptLineOut(SQLModel):
    seq: int = Field(description="줄 번호 (0부터)")
    speaker_user_id: int | None = Field(description="말한 사람. 모르면 null")
    speaker_name: str | None = Field(description="말한 사람 이름. 모르면 null")
    text: str = Field(description="발언")


class MinutesOut(SQLModel):
    headline: str = Field(description="주제 한 줄")
    status: MinutesStatus = Field(description="요약 상태 (summarizing / done / failed)")
    decisions: list[str] = Field(description="결정")
    discussions: list[str] = Field(description="논의")
    pendings: list[str] = Field(description="보류")


class MeetingTaskOut(SQLModel):
    """이 회의에서 확정된 할 일."""

    id: int = Field(description="할 일 ID")
    title: str = Field(description="제목")
    due_date: date | None = Field(description="기한. 없으면 null")
    assignee_user_id: int | None = Field(description="담당자. 없으면 null (담당자 없음)")
    assignee_name: str | None = Field(description="담당자 이름")
    state: TaskState = Field(description="상태 (todo / doing / blocked / done)")
    confirmed_by_name: str | None = Field(description="확정한 사람 이름")
    confirmed_at: datetime | None = Field(description="확정한 시각")


class SuggestionOut(SQLModel):
    """확정 전 AI 제안. 할 일 목록에는 나오지 않는다."""

    id: int = Field(description="제안 ID")
    title: str = Field(description="제목")
    due_date: date | None = Field(description="기한. 없으면 null")
    assignee_user_id: int | None = Field(description="담당자. 대개 비어 있다")
    assignee_name: str | None = Field(description="담당자 이름")


class MeetingDetailOut(SQLModel):
    """회의록 보기. 원문 + 요약 + 확정된 할 일 + AI 제안."""

    id: int = Field(description="회의 ID")
    topic: str = Field(description="회의 주제")
    start_at: datetime = Field(description="시작 시각")
    end_at: datetime = Field(description="끝 시각")
    mode: Mode = Field(description="대면(offline)·비대면(online)")
    status: MeetingStatus = Field(description="회의 상태")
    transcript_mode: TranscriptMode | None = Field(
        description="기록 방식 (stt 받아적기 / manual 직접 쓰기). 기록 전이면 null"
    )
    attendees: list[PersonOut] = Field(description="참석자 (수락한 사람)")
    transcript: list[TranscriptLineOut] = Field(description="원문. 줄 번호 순")
    minutes: MinutesOut | None = Field(description="요약. 요약 전이면 null")
    tasks: list[MeetingTaskOut] = Field(description="이 회의에서 확정된 할 일")
    suggestions: list[SuggestionOut] = Field(description="확정 전 AI 제안")


class MeetingSummaryOut(SQLModel):
    """회의록 목록의 한 줄."""

    id: int = Field(description="회의 ID")
    topic: str = Field(description="회의 주제")
    headline: str | None = Field(description="회의록 주제 한 줄. 요약 전이면 null")
    start_at: datetime = Field(description="시작 시각")
    mode: Mode = Field(description="대면·비대면")
    status: MeetingStatus = Field(description="회의 상태")
    attendees: list[str] = Field(description="참석자 이름")
    has_transcript: bool = Field(description="원문이 있는지")
    suggestion_count: int = Field(description="확정 전 AI 제안 수")


class MeetingListOut(SQLModel):
    meetings: list[MeetingSummaryOut] = Field(description="최근 회의가 먼저")
