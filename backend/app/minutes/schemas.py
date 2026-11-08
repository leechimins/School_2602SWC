"""회의록 · 제안 · 할 일이 주고받는 모양. table=True가 없는 모델만 있다.

Field의 description은 Swagger에 그대로 보인다.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from app.shared.enums import (
    MeetingStatus,
    MinutesStatus,
    Mode,
    TaskState,
    TranscriptMode,
)

# ── Record 입력 ─────────────────────────────────────────────────────


class RecordStartIn(SQLModel):
    """회의 기록 시작. 잡힌 회의에 붙이거나, 없으면 새로 만든다.

    둘 중 하나만 보낸다. Swagger 기본 예시가 meeting_id=0을 채워 404가
    나는 일이 있어서, 두 경우를 예시로 따로 보여 준다.
    """

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"topic": "최종 발표 역할 나누기", "mode": "offline"},
                {"meeting_id": 2},
            ]
        }
    }

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


class SegmentIn(SQLModel):
    """받아적은 한 줄."""

    seq: int = Field(ge=0, le=100_000, description="줄 번호. 0부터 하나씩. 같은 번호를 다시 보내면 건너뜀")
    speaker_label: str | None = Field(
        default=None, max_length=8, description='엔진이 붙인 목소리 라벨("A" 등). 없으면 null'
    )
    text: str = Field(min_length=1, max_length=1000, description="받아적은 글. 공백만 있으면 400")

    @field_validator("text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        # 공백만 있는 줄을 조용히 버리면 그 번호가 영영 missing에 남아
        # 프론트가 끝없이 다시 보낸다. 받기 전에 분명히 거절한다.
        value = value.strip()
        if not value:
            raise ValueError("빈 줄은 보낼 수 없습니다.")
        return value


class SegmentsIn(SQLModel):
    """받아적은 줄을 여러 개 한 번에. 끊겼다 다시 보내도 된다."""

    segments: list[SegmentIn] = Field(min_length=1, max_length=50, description="한 번에 50줄까지")


class SegmentsOut(SQLModel):
    added: int = Field(description="이번에 새로 쌓인 줄 수")
    skipped: int = Field(description="이미 있던 번호라 건너뛴 줄 수")
    last_seq: int = Field(description="지금까지 받은 가장 큰 줄 번호")
    missing: list[int] = Field(
        description="0부터 last_seq 사이에서 아직 안 온 번호(앞에서 100개까지). 이것만 다시 보내면 됨"
    )


class SpeakerMappingIn(SQLModel):
    """말한 사람 정하기. 둘 다 비워도 되고, 같이 보내면 줄마다 고친 것이 이긴다."""

    labels: dict[str, int | None] = Field(
        default_factory=dict,
        description='목소리 라벨 → 팀원 ID. 그 라벨의 모든 줄에 한 번에 반영. null은 "모름". 예: {"A": 3, "B": null}',
    )
    lines: dict[int, int | None] = Field(
        default_factory=dict,
        description='줄 번호 → 팀원 ID. 라벨 연결보다 우선. null은 "모름". 예: {"7": 5}',
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
    speaker_label: str | None = Field(
        description='받아적기 엔진이 붙인 목소리 라벨("A" 등). 말한 사람 고르기 화면용. 직접 쓰기면 null'
    )
    speaker_user_id: int | None = Field(description="말한 사람. 모르면 null")
    speaker_name: str | None = Field(description="말한 사람 이름. 모르면 null")
    text: str = Field(description="발언")


class MinutesOut(SQLModel):
    headline: str = Field(description="주제 한 줄")
    status: MinutesStatus = Field(description="요약 상태 (summarizing / done / failed)")
    decisions: list[str] = Field(description="결정")
    discussions: list[str] = Field(description="논의")
    pendings: list[str] = Field(description="보류")


class TaskSourceOut(SQLModel):
    """할 일이 나온 회의. 화면의 "11/5 회의" 출처 표시."""

    meeting_id: int = Field(description="회의 ID")
    held_on: date = Field(description="회의 날짜")
    topic: str = Field(description="회의 주제")


class TaskOut(SQLModel):
    """할 일 한 줄. 할 일 목록 · 할 일 하나 · 회의록 안 · 제안 확정 응답이 모두 이 모양이다."""

    id: int = Field(description="할 일 ID")
    title: str = Field(description="제목")
    due_date: date | None = Field(description="기한. 없으면 null")
    assignee_user_id: int | None = Field(description="담당자. 없으면 null (담당자 없음)")
    assignee_name: str | None = Field(description="담당자 이름")
    state: TaskState = Field(description="상태 (todo 시작 전 / doing 진행 중 / blocked 막힘 / done 완료)")
    source: TaskSourceOut | None = Field(description="출처 회의. 직접 추가면 null")
    confirmed_by_name: str | None = Field(description='확정한 사람 이름. "확정 · 확정한 사람" 뱃지')
    confirmed_at: datetime | None = Field(description="확정한 시각")
    is_late: bool = Field(description="늦음 뱃지. 기한이 시연 시계의 오늘보다 앞서고 완료가 아님")
    can_change_status: bool = Field(
        description="상태를 바꿀 수 있는지. 담당자만, 담당자가 없으면 전원"
    )
    can_edit: bool = Field(description="제목·담당자·기한 고치기와 필요 없음. 전원 true")


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
    recording_state: Literal["none", "recording", "stopped"] = Field(
        description="받아적기 상태. none 시작 전(또는 직접 쓰기) / recording 받아적는 중 / stopped 멈춤"
    )
    attendees: list[PersonOut] = Field(description="참석자 (수락한 사람)")
    transcript: list[TranscriptLineOut] = Field(description="원문. 줄 번호 순")
    minutes: MinutesOut | None = Field(description="요약. 요약 전이면 null")
    tasks: list[TaskOut] = Field(description="이 회의에서 확정된 할 일. 할 일 목록과 같은 모양")
    done_tasks: list[TaskOut] = Field(
        description='이 회의에서 끝났다고 말해 완료로 바뀐 할 일("회의에서 끝난 일"). 할 일 목록과 같은 모양'
    )
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


# ── Suggest ─────────────────────────────────────────────────────────


class ConfirmIn(SQLModel):
    """제안 한꺼번에 확정."""

    suggestion_ids: list[int] = Field(
        min_length=1, max_length=50, description="확정할 제안 ID들. 하나만 보내도 된다"
    )


class SuggestionPatch(SQLModel):
    """제안 고치기. 보낸 칸만 바꾼다. 담당자·기한은 null을 보내면 비운다."""

    title: str | None = Field(default=None, min_length=1, max_length=200, description="제목")
    assignee_user_id: int | None = Field(
        default=None, description="담당자. 이 방 팀원만. null이면 담당자 없음"
    )
    due_date: date | None = Field(default=None, description="기한. null이면 기한 없음")


class ConfirmOut(SQLModel):
    tasks: list[TaskOut] = Field(description="방금 확정된 할 일. 할 일 목록과 같은 모양")


# ── Task ────────────────────────────────────────────────────────────


class TaskCountOut(SQLModel):
    user_id: int = Field(description="팀원 ID")
    name: str = Field(description="이름")
    remaining: int = Field(description="남은 할 일 수 (완료·필요 없음 제외)")


class TaskListOut(SQLModel):
    """팀 할 일."""

    tasks: list[TaskOut] = Field(
        description="담당자 없음 → 나 → 다른 사람 순. 묶음 안에서는 기한 순"
    )
    task_counts: list[TaskCountOut] = Field(description="사람별 남은 할 일 수")
    suggestion_count: int = Field(
        description="확정 전 AI 제안 수. 0보다 크면 '회의록에 제안 N개' 안내"
    )


class MyTaskListOut(SQLModel):
    tasks: list[TaskOut] = Field(description="내가 담당인 할 일. 기한 순, 기한 없으면 맨 뒤")


class StatusIn(SQLModel):
    state: TaskState = Field(description="바꿀 상태")


class TaskPatch(SQLModel):
    """할 일 고치기. 보낸 칸만 바꾼다. 담당자·기한은 null을 보내면 비운다."""

    title: str | None = Field(default=None, min_length=1, max_length=200, description="제목")
    assignee_user_id: int | None = Field(
        default=None, description="담당자. 이 방 팀원만. null이면 담당자 없음"
    )
    due_date: date | None = Field(default=None, description="기한. null이면 기한 없음")


class TaskCreateIn(SQLModel):
    """할 일 직접 추가. AI 없이 도는 길."""

    title: str = Field(min_length=1, max_length=200, description="제목")
    assignee_user_id: int | None = Field(default=None, description="담당자. 비워도 됨")
    due_date: date | None = Field(default=None, description="기한. 비워도 됨")
    meeting_id: int | None = Field(
        default=None,
        description="출처 회의. 회의록에서 추가하면 그 회의, 비우면 직접 추가(source가 null)",
    )


class ReassignIn(SQLModel):
    assignee_user_id: int | None = Field(description="새 담당자. null이면 담당자 없음")
