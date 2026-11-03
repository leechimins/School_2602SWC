"""Meeting 도메인 — 조율부터 회의 확정까지. 레인 A.

조율 한 번이 DB에 남기는 순서는 db-설계.md §6에 적혀 있다. 요약하면:
scheduling 한 행 → candidate_slot + slot_cost(계산만, LLM 없음) →
utterance가 쌓임 → meeting(proposed) + meeting_response(pending) →
전원 수락 → meeting(confirmed) + yield_entry.

조율은 사람이 사정을 적어 넣지 않아도 돈다. 읽는 것은 schedule_item,
preference, slot_cost, 그리고 membership.yield_total 넷이다. 라운드 조정은
마지막 것으로 일어난다 — total_cost가 조금 더 비싼 후보라도 누적 양보가
높은 사람의 score가 낮은 쪽을 고른다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, Index, UniqueConstraint, text
from sqlmodel import Field, SQLModel

from app.shared.base import enum_text, in_check, ts
from app.shared.enums import (
    MeetingStatus,
    Mode,
    ResponseState,
    SchedulingStatus,
    SpeakerKind,
    TranscriptMode,
)


class Scheduling(SQLModel, table=True):
    """조율 한 번. 팀장이 연다."""

    __tablename__ = "scheduling"
    __table_args__ = (
        CheckConstraint(in_check("status", SchedulingStatus), name="ck_sched_status"),
        CheckConstraint(in_check("mode", Mode), name="ck_sched_mode"),
        # 회의는 30분 단위다. 길이도 30의 배수여야 한다.
        CheckConstraint(
            "duration_min > 0 AND duration_min % 30 = 0", name="ck_sched_duration"
        ),
        CheckConstraint("window_start <= window_end", name="ck_sched_window"),
        CheckConstraint("rounds_used BETWEEN 0 AND 3", name="ck_sched_rounds"),
        # 한 방에 도는 조율은 하나만. 조율이 도는 중에 팀장이 한 번 더 누르는
        # 일은 쉽게 일어나고, 그러면 발언이 두 줄기로 섞여 핵심 화면이 망가진다.
        # Postgres 부분 인덱스라 running이 아닌 행은 몇 개든 상관없다.
        Index(
            "ix_one_running_scheduling_per_room",
            "room_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    room_id: int = Field(foreign_key="room.id", ondelete="CASCADE", index=True)
    started_by: int = Field(foreign_key="user.id", ondelete="CASCADE")

    topic: str = Field(max_length=100)
    # "언제부터 언제 사이에"
    window_start: datetime = ts()
    window_end: datetime = ts()
    duration_min: int
    mode: Mode = enum_text(length=10)

    status: SchedulingStatus = enum_text(length=12)
    rounds_used: int = Field(default=0)

    created_at: datetime = ts(auto_now=True)
    closed_at: datetime | None = ts(nullable=True)


class CandidateSlot(SQLModel, table=True):
    """후보 시간. 채점기가 만든 것이 다 남는다.

    제안한 것도, 거절당한 것도, 못 고른 것도 남긴다. 시연에서 심사위원이
    "왜 이 시간이죠"라고 물으면 열어 보여 줄 근거다. 3라운드 안에 합의가
    실패했을 때 사람이 고를 후보도 여기서 꺼낸다.
    """

    __tablename__ = "candidate_slot"
    __table_args__ = (
        CheckConstraint("start_at < end_at", name="ck_candidate_range"),
        CheckConstraint("round_no BETWEEN 1 AND 3", name="ck_candidate_round"),
    )

    id: int | None = Field(default=None, primary_key=True)
    scheduling_id: int = Field(
        foreign_key="scheduling.id", ondelete="CASCADE", index=True
    )

    start_at: datetime = ts()  # 분은 0 또는 30
    end_at: datetime = ts()
    total_cost: float  # 팀 전체 불편 합
    round_no: int
    proposed: bool = Field(default=False)  # 판단 에이전트가 실제로 제안했나
    # 1명 불참안이면 빠지는 사람. 전원 가능한 시간이 없을 때만 찬다.
    absentee_user_id: int | None = Field(
        default=None, foreign_key="user.id", ondelete="CASCADE"
    )

    created_at: datetime = ts(auto_now=True)


class SlotCost(SQLModel, table=True):
    """사람별 불편.

    score는 계산이 정한다. 에이전트가 정하지 않는다 — 그래서 리허설과 본
    시연이 같은 답을 낸다.

    본인에게만 숫자로 보인다. 남의 score는 괜찮음/조금/많이로 바꿔
    내보낸다(명세 권장 규칙 3). 응답에 담으면 제품의 핵심 약속이 깨진다.
    """

    __tablename__ = "slot_cost"
    __table_args__ = (
        UniqueConstraint("candidate_slot_id", "user_id", name="uq_slot_cost"),
        CheckConstraint("score BETWEEN 1 AND 5", name="ck_slot_cost_score"),
    )

    id: int | None = Field(default=None, primary_key=True)
    candidate_slot_id: int = Field(
        foreign_key="candidate_slot.id", ondelete="CASCADE", index=True
    )
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE")

    score: int  # 1~5. 1 = 괜찮음
    available: bool = Field(default=True)  # false면 그 시간에 아예 안 된다
    # 에이전트가 말할 이유 한 줄. 겹치는 schedule_item과
    # preference.avoid_polished에서 만든다.
    reason: str = Field(max_length=200)


class Utterance(SQLModel, table=True):
    """조율 발언.

    "시간 정하는 과정" 화면이 하나씩 꺼내 보여 주는 줄들이다. 이 10~20초는
    로딩이 아니라 구경거리라서, 스피너를 돌리면 시연에서 가장 중요한 장면을
    덮는다.

    SSE가 seq 다음 것부터 흘려보낸다. 새로 들어와도 처음부터 다시 볼 수 있다.
    """

    __tablename__ = "utterance"
    __table_args__ = (
        UniqueConstraint("scheduling_id", "seq", name="uq_utterance_seq"),
        CheckConstraint(in_check("speaker_kind", SpeakerKind), name="ck_utt_speaker"),
        CheckConstraint("round_no BETWEEN 1 AND 3", name="ck_utt_round"),
        # 팀원 에이전트는 누구인지가 있어야 하고, 판단 에이전트는 없어야 한다.
        CheckConstraint(
            "(speaker_kind = 'member' AND speaker_user_id IS NOT NULL) "
            "OR (speaker_kind = 'judge' AND speaker_user_id IS NULL)",
            name="ck_utt_speaker_shape",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    scheduling_id: int = Field(
        foreign_key="scheduling.id", ondelete="CASCADE", index=True
    )

    round_no: int
    seq: int  # 화면에 나올 순서
    speaker_kind: SpeakerKind = enum_text(length=8)
    speaker_user_id: int | None = Field(
        default=None, foreign_key="user.id", ondelete="CASCADE"
    )
    text: str = Field(max_length=500)

    created_at: datetime = ts(auto_now=True)


class Meeting(SQLModel, table=True):
    """회의. status='proposed'인 행이 곧 "회의안"이다.

    별도 proposal 테이블을 두지 않은 이유는 db-설계.md §0에 적혀 있다.
    전원 수락으로 확정될 때 행을 옮기지 않고 status만 바꾸므로, 일정 화면이
    "조율 중인 회의도 자리를 잡아 둔다"를 meeting 전체 조회 하나로 그린다.

    아키텍처 문서의 두 사람 계약 Meeting { id, slot, attendees, why }가 이
    행이다. slot = start_at/end_at, attendees = meeting_response, why = rationale.

    레인이 갈리는 유일한 테이블이다. A가 proposed→confirmed까지 쓰고,
    그 뒤 기록 칸(transcript_*, recording_*)은 B(Record)가 쓴다.
    같은 행의 다른 칸을 나눠 쓰는 것이니 서로 남의 칸을 건드리지 않는다.
    """

    __tablename__ = "meeting"
    __table_args__ = (
        CheckConstraint("start_at < end_at", name="ck_meeting_range"),
        CheckConstraint(in_check("status", MeetingStatus), name="ck_meeting_status"),
        # 확정된 회의는 대면·비대면 중 하나로 정해진다. any가 들어가면 안 된다.
        CheckConstraint("mode IN ('offline', 'online')", name="ck_meeting_mode"),
        CheckConstraint(
            f"transcript_mode IS NULL OR {in_check('transcript_mode', TranscriptMode)}",
            name="ck_meeting_transcript_mode",
        ),
        # 확정 시각은 확정된 뒤에만 있다.
        CheckConstraint(
            "(status = 'proposed' AND confirmed_at IS NULL) OR status <> 'proposed'",
            name="ck_meeting_confirmed_at",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    room_id: int = Field(foreign_key="room.id", ondelete="CASCADE", index=True)
    # 조율 없이 만든 회의면 비운다 — 명세의 POST /rooms/{id}/meetings가
    # "확정된 회의 없이도 됨"이라고 적었다.
    scheduling_id: int | None = Field(
        default=None, foreign_key="scheduling.id", ondelete="SET NULL"
    )
    candidate_slot_id: int | None = Field(
        default=None, foreign_key="candidate_slot.id", ondelete="SET NULL"
    )

    topic: str = Field(max_length=100)
    start_at: datetime = ts(index=True)
    end_at: datetime = ts()
    mode: Mode = enum_text(length=10)
    status: MeetingStatus = enum_text(length=12)
    # 판단 에이전트가 쓴 1~3문장. 왜 이 시간인지.
    rationale: str = Field(default="", max_length=500)
    confirmed_at: datetime | None = ts(nullable=True)

    # --- 여기부터 B(Record)가 쓰는 칸. A는 읽지도 쓰지도 않는다. ---
    transcript_mode: TranscriptMode | None = enum_text(nullable=True, length=8)
    recording_started_at: datetime | None = ts(nullable=True)
    recording_stopped_at: datetime | None = ts(nullable=True)

    created_at: datetime = ts(auto_now=True)


class MeetingResponse(SQLModel, table=True):
    """수락·거절.

    회의안이 만들어질 때 팀원 수만큼 pending으로 미리 깔아 둔다 — 그래야
    "누가 아직 안 답했는지"를 이름으로 보여 줄 수 있다.

    전원 accepted가 되는 그 요청 안에서 meeting.status='confirmed',
    confirmed_at, yield_entry, membership.yield_total, 알림까지 한
    트랜잭션으로 처리한다. 확정 버튼이 없으므로 다른 기회가 없다.

    그 트랜잭션은 meeting 행을 FOR UPDATE로 잠그고 시작한다. 안 잠그면
    마지막 두 사람이 같은 순간에 누를 때 아무도 확정하지 않거나 양보
    점수가 두 번 들어간다. 시연이 한 화면에 폰 둘을 띄우는 구조라 실제로
    일어난다.
    """

    __tablename__ = "meeting_response"
    __table_args__ = (
        UniqueConstraint("meeting_id", "user_id", name="uq_meeting_response"),
        CheckConstraint(in_check("state", ResponseState), name="ck_response_state"),
        # 답한 사람은 답한 시각이 있고, 안 답한 사람은 없다.
        CheckConstraint(
            "(state = 'pending' AND responded_at IS NULL) "
            "OR (state <> 'pending' AND responded_at IS NOT NULL)",
            name="ck_response_shape",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    meeting_id: int = Field(foreign_key="meeting.id", ondelete="CASCADE", index=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE")

    state: ResponseState = enum_text(length=10)
    # 수락·거절 확인 창에 남긴 한 줄. 비어도 된다.
    feedback: str | None = Field(default=None, max_length=200)
    responded_at: datetime | None = ts(nullable=True)


class YieldEntry(SQLModel, table=True):
    """양보 장부.

    차등은 불편 점수에서 나온다. 2~3점 → +1, 4~5점 → +2, 1점(괜찮음)은
    행을 만들지 않는다.

    회의가 확정될 때 한 번만 만든다. membership.yield_total도 같은
    트랜잭션에서 올린다.

    회의별로 누가 왜 맞춰 줬는지가 팀 화면에 나오는 기록이다.
    """

    __tablename__ = "yield_entry"
    __table_args__ = (
        CheckConstraint("points IN (1, 2)", name="ck_yield_points"),
        CheckConstraint("discomfort BETWEEN 2 AND 5", name="ck_yield_discomfort"),
        # 한 회의에서 한 사람이 양보 점수를 두 번 받지 않는다.
        UniqueConstraint("meeting_id", "user_id", name="uq_yield_meeting_user"),
    )

    id: int | None = Field(default=None, primary_key=True)
    room_id: int = Field(foreign_key="room.id", ondelete="CASCADE", index=True)
    meeting_id: int = Field(foreign_key="meeting.id", ondelete="CASCADE")
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)

    points: int  # +1 또는 +2
    discomfort: int  # 근거가 된 불편 점수 2~5
    # "내 불편 3/5만큼 맞춰 줘서 +1"
    reason: str = Field(max_length=200)

    created_at: datetime = ts(auto_now=True)


class PreferenceChange(SQLModel, table=True):
    """피드백이 바꾼 것.

    말없이 바꾸면 안 된다. 이 행이 곧 화면에 보이는 "무엇이 어떻게
    바뀌었는지 한 줄"이다. 행을 안 만들고 preference만 고치는 길은 없다.

    아무것도 안 바뀌면 행을 만들지 않는다. 적은 말이 시간과 상관없을 때
    억지로 무언가 바꾸지 않는다.

    되돌리기는 before를 preference에 다시 쓰고 reverted=true로 둔다.
    행을 지우지 않는다 — 명세의 POST /me/preference-changes/{id}/undo다.
    """

    __tablename__ = "preference_change"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    # 어느 응답에서 나왔나.
    meeting_id: int | None = Field(
        default=None, foreign_key="meeting.id", ondelete="SET NULL"
    )

    source_text: str = Field(max_length=200)  # 사람이 적은 한 줄
    field: str = Field(max_length=30)  # 바뀐 preference 열 이름
    before: str | None = Field(default=None, max_length=200)
    after: str | None = Field(default=None, max_length=200)
    # "다음부터 11시 이전은 피할게요"
    summary: str = Field(max_length=200)
    reverted: bool = Field(default=False)

    created_at: datetime = ts(auto_now=True)
