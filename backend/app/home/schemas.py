"""홈 한 화면이 주고받는 모양. table=True가 없는 모델만 있다.

홈은 **읽기만 하는 화면**이라 들어오는 입력이 없다. 그래서 이 파일에는
나가는 모양만 있다.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from sqlmodel import SQLModel

from app.shared.enums import MeetingStatus, ResponseState, SchedulingStatus, TaskState

# 내 할 일을 묶는 다섯 갈래. 브리프: "기한 지남 / 오늘 / 내일 / 그 이후 / 완료".
#
# shared/enums.py에 넣지 않은 이유는 홈 화면 바깥에서 쓸 데가 없어서다.
# 그 파일은 두 레인이 같이 읽어서, 한쪽에서만 쓰는 값을 더하면 상대가
# 안 쓰는 열거값을 떠안는다.
TaskBucket = Literal["late", "today", "tomorrow", "later", "done"]


class NextMeeting(SQLModel):
    """다음 회의 하나. 일정 탭과 달리 홈은 **하나만** 요약해 보여 준다."""

    id: int
    topic: str
    start_at: datetime
    end_at: datetime
    mode: str
    status: MeetingStatus
    # 조정으로 정해졌나. 화면이 "확정 · 조정"으로 그린다.
    settled: bool = False
    my_state: ResponseState | None = None
    accepted: int = 0
    # 응답할 사람 수. 1명 불참안이면 빠지는 사람은 빠진다.
    responders: int = 0


class Coordinating(SQLModel):
    """아직 도는 조율. 잡힌 회의가 없어도 홈이 "조율 중"을 보여 준다."""

    id: int
    topic: str
    window_start: datetime
    window_end: datetime
    status: SchedulingStatus


class MyTask(SQLModel):
    """내 할 일 한 줄. 기한 순 하나로만 보여 준다(브리프)."""

    id: int
    title: str
    due_date: date | None = None
    state: TaskState
    bucket: TaskBucket
    # 뱃지 둘. 브리프: "홈에서는 종의 숫자와 내 할 일 옆 늦음·막힘 뱃지로 충분".
    late: bool = False
    blocked: bool = False


class HomeOut(SQLModel):
    """홈 탭 한 화면.

    한 번에 주는 이유: 이 화면을 나눠 받으면 방·일정·할 일·알림을 네 번
    불러야 하는데, 홈은 앱을 열 때마다 처음 보는 화면이라 그게 그대로
    첫 로딩 시간이 된다.

    **오늘이 서버에서 온다.** 디데이도 할 일 묶음도 "오늘"을 기준으로
    갈리는데, 프론트가 자기 시계로 계산하면 시연에서 날짜를 앞으로 옮겼을 때
    서버가 보낸 묶음과 화면의 디데이가 어긋난다.
    """

    # 기간 카드. 막대와 오늘 위치는 셋으로 프론트가 그린다.
    today: date
    start_date: date
    due_date: date
    # 마감까지 남은 날. 오늘이 마감이면 0, 지났으면 음수.
    d_day: int

    next_meeting: NextMeeting | None = None
    coordinating: Coordinating | None = None
    my_tasks: list[MyTask] = []
    unread_notifications: int = 0

    # 새 회의 잡기 버튼을 보일지(명세 권장 규칙 4). 홈에만 있는 버튼이다.
    can_start_scheduling: bool = False
    # 방을 막 만든 직후 화면에 쓴다 — 초대 코드와 들어온 인원.
    invite_code: str
    joined_count: int
    member_count: int
