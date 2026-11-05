"""모델이 공통으로 쓰는 조각들.

시각을 다루는 규칙이 여기 한곳에 모여 있다. API 명세의 권장 규칙 2가
"시각에 오프셋(+09:00)을 붙임"이고, 안 지키면 시연 시계를 옮겼을 때
늦음 판정과 30분 전 알림이 어긋난다고 못박았다. 그래서 DB 열을 전부
TIMESTAMPTZ로 두고 aware datetime만 넣는다. naive가 섞이면 비교에서
TypeError가 나므로 조용히 틀리지 않고 일찍 터진다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, DateTime, String
from sqlalchemy import Integer
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import Field

KST = timezone(timedelta(hours=9))


def real_now() -> datetime:
    """실제 시각. 시연 시계를 거치지 않는다.

    판정에 쓰는 "지금"은 이게 아니라 shared.demo_clock.now(session)다.
    여기는 created_at처럼 기록용 시각에만 쓴다.
    """
    return datetime.now(KST)


def ts(*, nullable: bool = False, index: bool = False, auto_now: bool = False) -> Any:
    """TIMESTAMPTZ 열.

    SQLModel의 datetime은 기본으로 타임존 없는 TIMESTAMP가 되므로
    sa_column을 직접 준다. 열마다 쓰다 보니 한 줄로 묶었다.
    """
    column = Column(DateTime(timezone=True), nullable=nullable, index=index)
    if auto_now:
        return Field(default_factory=real_now, sa_column=column)
    if nullable:
        return Field(default=None, sa_column=column)
    return Field(sa_column=column)


def enum_text(*, nullable: bool = False, index: bool = False, length: int = 20) -> Any:
    """열거값을 담는 text 열.

    주석을 달아 두는 이유: 그냥 `status: MeetingStatus`로 두면 SQLModel이 Postgres
    네이티브 ENUM 타입을 만든다. 그러면 값 하나 더할 때마다 ALTER TYPE이
    필요해서, 기획이 움직이는 2주 동안 계속 걸린다. 그래서 열은 text로
    두고 파이썬 쪽 타입만 StrEnum으로 남긴다 — 들어오는 값은 Pydantic이,
    DB에 박히는 값은 CHECK(in_check)가 지킨다.
    """
    column = Column(String(length), nullable=nullable, index=index)
    if nullable:
        return Field(default=None, sa_column=column)
    return Field(sa_column=column)


def enum_text_array(*, nullable: bool = True) -> Any:
    """열거값 여러 개를 담는 text[] 열. 온보딩 질문 3(시간대 여러 개)에 쓴다."""
    column = Column(ARRAY(String(20)), nullable=nullable)
    if nullable:
        return Field(default=None, sa_column=column)
    return Field(sa_column=column)


def int_array(*, nullable: bool = True) -> Any:
    """정수 여러 개를 담는 integer[] 열. 피하고 싶은 요일(0~6)에 쓴다.

    요일을 따로 테이블로 빼지 않는 이유는 enum_text_array와 같다 — 값이
    고정이고 조건 검색을 안 한다. 한 사람이 한 구간만 갖는다.
    """
    column = Column(ARRAY(Integer), nullable=nullable)
    if nullable:
        return Field(default=None, sa_column=column)
    return Field(sa_column=column)


def in_check(column: str, enum_cls: type[StrEnum]) -> str:
    """열거값을 CHECK 제약 문구로 바꾼다.

    Postgres 네이티브 ENUM을 쓰지 않는 이유는 db-설계.md §0에 적어 뒀다.
    값 하나 더할 때마다 ALTER TYPE이 필요한데 기획이 아직 움직인다.
    """
    values = ", ".join(f"'{member.value}'" for member in enum_cls)
    return f"{column} IN ({values})"
