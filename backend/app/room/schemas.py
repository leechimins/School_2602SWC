"""Room이 주고받는 모양. table=True가 없는 모델만 있다.

table=True 모델은 Pydantic 검사가 꺼지므로 입력은 여기서 받는다.

남의 점수 숫자를 담는 칸을 아예 두지 않는다. 누적 양보는 YieldLevel
단계로만 나간다 — 칸이 없으면 실수로 채울 수도 없다.

Field의 description은 Swagger에 그대로 보인다. 프론트가 읽는 설명이다.
"""

from __future__ import annotations

from datetime import date

from sqlmodel import Field, SQLModel

from app.shared.enums import YieldLevel


class RoomCreateIn(SQLModel):
    """방 생성하기 화면의 입력."""

    name: str = Field(min_length=1, max_length=100, description="과제 제목 (방 이름)")
    description: str = Field(default="", max_length=500, description="과제 설명 두세 줄")
    start_date: date = Field(description="시작일 (YYYY-MM-DD)")
    due_date: date = Field(description="마감일 (YYYY-MM-DD). 마감 디데이의 기준")
    # 11/4 브리프에서 방 만들기 화면의 평가 방식 칸이 빠졌다. 예전 프론트가 보내도
    # 받도록 칸은 남기고 선택으로 둔다(테이블 칸이 NOT NULL이라 빈 글자로 저장).
    eval_method: str = Field(
        default="", max_length=50, description="평가 방식. 선택 — 화면에서 빠짐(11/4)"
    )
    member_count: int = Field(ge=2, le=6, description="팀원 수 (2~6명). 정원으로 쓴다")


class JoinIn(SQLModel):
    """초대 코드로 들어가기."""

    invite_code: str = Field(
        min_length=6, max_length=6, description="초대 코드 6자리. 대소문자 상관없음"
    )


class MyRoomOut(SQLModel):
    """내가 속한 방 하나."""

    id: int = Field(description="방 ID")
    name: str = Field(description="방 이름")
    is_leader: bool = Field(description="내가 이 방의 팀장인지")


class MeOut(SQLModel):
    """내 계정."""

    user_id: int = Field(description="내 사용자 ID")
    name: str = Field(description="내 이름")
    rooms: list[MyRoomOut] = Field(description="속한 방 목록. 없으면 빈 목록")


class MemberOut(SQLModel):
    """팀원 한 명."""

    user_id: int = Field(description="사용자 ID")
    name: str = Field(description="이름")
    part: str | None = Field(description="역할 (자료조사·발표 등). 없으면 null")
    is_leader: bool = Field(description="팀장인지")
    is_me: bool = Field(description="보고 있는 본인인지")
    yield_level: YieldLevel = Field(
        description="누적 양보 단계. none=아직 없음, some=조금 맞춰 줌, much=많이 맞춰 줌"
    )


class RoomOut(SQLModel):
    """방 정보. 팀 화면이 이것 하나로 그려진다."""

    id: int = Field(description="방 ID")
    name: str = Field(description="방 이름")
    description: str = Field(description="과제 설명")
    start_date: date = Field(description="시작일")
    due_date: date = Field(description="마감일")
    d_day: int = Field(description="마감까지 남은 날. 시연 시계의 오늘 기준, 지나면 음수")
    eval_method: str = Field(description="평가 방식")
    member_count: int = Field(description="정원")
    joined_count: int = Field(description="지금 들어온 인원")
    invite_code: str = Field(description="초대 코드 6자리")
    leader_user_id: int = Field(description="팀장의 사용자 ID")
    members: list[MemberOut] = Field(description="팀원 목록. 팀장이 맨 위")
    can_start_scheduling: bool = Field(
        description="회의 조율을 시작할 수 있는지 (팀장만 true). 프론트는 이 값으로 버튼을 보인다"
    )


class InvitePreviewOut(SQLModel):
    """초대 코드 미리보기. 방 이름과 인원만."""

    name: str = Field(description="방 이름")
    member_count: int = Field(description="정원")
    joined_count: int = Field(description="지금 들어온 인원")
