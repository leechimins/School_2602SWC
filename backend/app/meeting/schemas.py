"""조율이 주고받는 모양. table=True가 없는 모델만 있다.

여기서 지켜야 하는 약속이 하나 있다 — **남의 점수는 응답에 담지 않는다**
(명세 권장 규칙 3). 내 불편 점수와 팀 전체 불편 합은 다른 종류다:
앞의 것은 본인에게 숫자로 보이고, 뒤의 것은 아무에게도 안 보인다.
total_cost가 이 파일의 어떤 클래스에도 없는 이유다.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.shared.enums import Mode, SchedulingStatus, SpeakerKind

# 점수를 "괜찮음 / 조금 / 많이"로 바꾸는 함수는 아직 없다. 그 말이 나가는
# 화면(회의 일정 조율 확인)이 회의안과 함께 오고, 회의안은 라운드를 돈
# 뒤에 생긴다. 쓰는 곳이 생길 때 같이 만든다.


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
