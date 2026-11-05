"""조율이 주고받는 모양. table=True가 없는 모델만 있다.

여기서 지켜야 하는 약속이 하나 있다 — **남의 점수는 응답에 담지 않는다**
(명세 권장 규칙 3). 내 불편 점수와 팀 전체 불편 합은 다른 종류다:
앞의 것은 본인에게 숫자로 보이고, 뒤의 것은 아무에게도 안 보인다.
total_cost가 이 파일의 어떤 클래스에도 없는 이유다.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.shared.enums import (
    Burden,
    MeetingStatus,
    Mode,
    ResponseState,
    SchedulingStatus,
    SpeakerKind,
    YieldLevel,
)

# 점수를 "괜찮음 / 조금 / 많이"로 바꾸는 것은 service.burden()이다.
# 계산이 아니라 내보내기 규칙이라 scorer가 아니라 service에 있다.


class SchedulingStartIn(SQLModel):
    """팀장이 조율 시작에서 넣는 것.

    브리프: 주제, 기간, 회의 길이(30분 단위), 방식(대면·비대면·상관없음).
    """

    topic: str = Field(min_length=1, max_length=100)
    window_start: datetime
    window_end: datetime
    # 길이 제한은 없고 30분 단위다. DB에도 같은 CHECK가 있다.
    duration_min: int = Field(gt=0, multiple_of=30)
    mode: Mode


class UtteranceOut(SQLModel):
    """조율 발언 한 줄. "시간 정하는 과정" 화면이 하나씩 꺼내 보여 준다."""

    seq: int
    round_no: int
    speaker_kind: SpeakerKind
    speaker_user_id: int | None = None
    speaker_name: str | None = None
    text: str
    created_at: datetime


class SchedulingOut(SQLModel):
    """조율 하나. 재진입해도 이걸로 화면을 다시 그린다.

    candidate_count는 "후보가 몇 개 나왔나"다. 점수가 아니라 개수라서
    내보내도 된다 — 0이면 화면이 바로 "전원 가능한 시간이 없다"로 간다.
    """

    id: int
    topic: str
    window_start: datetime
    window_end: datetime
    duration_min: int
    mode: Mode
    status: SchedulingStatus
    rounds_used: int
    candidate_count: int
    # can_* 권한 플래그(명세 권장 규칙 4)는 여기 없다. 조율을 시작할 수
    # 있는지는 홈 화면이 물어야 하는 것이고, rerun 권한은 아직 미정이다
    # (db-설계.md §9-5). 쓸 화면이 생길 때 그 응답에 붙인다.
    utterances: list[UtteranceOut] = []


class ResponderOut(SQLModel):
    """회의에 답할 사람 한 명. 내 칸이든 남의 칸이든 같은 모양이다.

    **score가 없다.** 남의 불편은 burden 세 단계로만 나간다(명세 권장
    규칙 3). 내 숫자는 ProposalOut.my_score에 따로 담는다 — 그래야 이
    목록을 그대로 화면에 뿌려도 남의 숫자가 샐 길이 없다.

    yield_level도 단계다. 누적 양보는 "현우가 지난번에 맞춰 줬다"를
    보여 주려고 있는 것이지 점수 순위표가 아니다.
    """

    user_id: int
    name: str
    state: ResponseState
    burden: Burden
    # "알바와 겹칩니다" — slot_cost.reason. 이미 다듬어진 문장이다.
    reason: str
    yield_level: YieldLevel
    feedback: str | None = None
    responded_at: datetime | None = None


class ProposalOut(SQLModel):
    """회의 하나. "회의 일정 조율 확인" 화면이 이걸로 그려진다.

    보는 사람마다 내용이 다르다 — my_*는 요청한 사람 것이다. 명세에
    "보는 사람마다 내용이 다름"이라고 적힌 이유다.
    """

    id: int
    topic: str
    start_at: datetime
    end_at: datetime
    mode: Mode
    status: MeetingStatus
    # 판단 에이전트가 쓴 "왜 이 시간인지".
    rationale: str
    # 합의(agreed)로 나온 안인지 조정(settled)으로 나온 안인지. 화면이
    # "확정 · 조정" 꼬리표와 "이미 확정됐습니다"를 이걸로 가른다.
    scheduling_status: SchedulingStatus | None = None

    my_score: int | None = None
    my_reason: str = ""
    # 이 회의로 내가 받는(받은) 양보 점수. 0이면 안 받는다.
    my_yield_points: int = 0
    my_state: ResponseState | None = None

    # 내가 수락·거절 버튼을 누를 수 있나(명세 권장 규칙 4).
    can_respond: bool = False
    # 조정된 안이라 이미 확정됐고 피드백만 받는 상태인가(브리프 11/5).
    feedback_only: bool = False

    responders: list[ResponderOut] = []


class RespondIn(SQLModel):
    """수락·거절 확인 창에서 보내는 것.

    feedback은 비워도 된다. 브리프: "다음부터는 오전 수업 끝나고가 좋아요"
    같은 한 줄이고, 적으면 내 선호에 반영된다.
    """

    accept: bool
    feedback: str | None = Field(default=None, max_length=200)


class RespondOut(SQLModel):
    """답한 뒤의 상태. 화면이 이걸로 다음 장면을 고른다."""

    meeting_id: int
    my_state: ResponseState
    meeting_status: MeetingStatus
    # 이번 요청으로 회의가 확정됐나. 마지막으로 수락한 사람만 참이다.
    confirmed_now: bool = False
    pending_count: int = 0
    declined_count: int = 0
    # 피드백만 저장했나(조정된 회의).
    feedback_only: bool = False


class MeetingBrief(SQLModel):
    """일정 목록에 한 줄로 나가는 회의."""

    id: int
    topic: str
    start_at: datetime
    end_at: datetime
    mode: Mode
    status: MeetingStatus
    # 조정으로 정해졌나. 참이면 화면이 "확정 · 조정"으로 그린다.
    settled: bool = False
    my_state: ResponseState | None = None
    pending_count: int = 0


class CoordinatingBrief(SQLModel):
    """아직 도는 조율. 잡힌 회의가 없어도 일정 화면에 자리를 잡아 둔다."""

    id: int
    topic: str
    window_start: datetime
    window_end: datetime
    status: SchedulingStatus


class ScheduleOut(SQLModel):
    """일정 보기(회의 관리) 한 화면.

    브리프 순서 그대로다 — 조율 중인 회의, 잡힌 회의, 지난 회의. 받아적기
    버튼은 upcoming 각 줄에 프론트가 붙인다(B 레인).

    지난 것과 다가오는 것을 서버가 가른다. 기준은 시연 시계다 — 프론트가
    자기 시계로 가르면 시연에서 날짜를 옮겼을 때 둘이 어긋난다.
    """

    coordinating: list[CoordinatingBrief] = []
    upcoming: list[MeetingBrief] = []
    past: list[MeetingBrief] = []
