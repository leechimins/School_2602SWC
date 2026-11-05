"""Onboard + MyPage 시간표 — preference · schedule_item. 레인 A.

조율이 읽는 재료가 전부 여기 있다. preference는 "사람이 원하는 것",
schedule_item은 "사람이 이미 묶여 있는 시간"이다. 빈칸 찾기가 둘을
겹쳐서 후보 시간을 만든다.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.shared.base import (
    enum_text,
    enum_text_array,
    in_check,
    int_array,
    ts,
)
from app.shared.enums import Daypart, Mode, Recurrence, ScheduleKind, ScheduleSource


class Preference(SQLModel, table=True):
    """온보딩 답 네 개.

    user와 1:1이다. 방마다 다르지 않다 — 온보딩은 한 번만 한다.

    네 개 모두 비어도 된다. 브리프에 "필수 항목은 없습니다. 네 개를 다 비워도
    다음으로 넘어갑니다"로 적혀 있다. 비면 빈칸 찾기에서 그 조건을 안 쓴다.
    """

    __tablename__ = "preference"
    __table_args__ = (
        CheckConstraint(
            "day_start_min IS NULL OR day_start_min BETWEEN 0 AND 1440",
            name="ck_preference_day_start_min",
        ),
        CheckConstraint(
            "day_end_min IS NULL OR day_end_min BETWEEN 0 AND 1440",
            name="ck_preference_day_end_min",
        ),
        CheckConstraint(
            "day_start_min IS NULL OR day_end_min IS NULL "
            "OR day_start_min < day_end_min",
            name="ck_preference_day_range",
        ),
        CheckConstraint(
            f"mode_pref IS NULL OR {in_check('mode_pref', Mode)}",
            name="ck_preference_mode",
        ),
        CheckConstraint(
            "avoid_start_min IS NULL OR avoid_start_min BETWEEN 0 AND 1440",
            name="ck_preference_avoid_start_min",
        ),
        CheckConstraint(
            "avoid_end_min IS NULL OR avoid_end_min BETWEEN 0 AND 1440",
            name="ck_preference_avoid_end_min",
        ),
        # 뒤집힌 구간은 받지 않는다. 자정을 넘는 "밤 22시~새벽 2시"는 못
        # 담는데, 그건 회의 시간대가 아니라서 지금은 버린다.
        CheckConstraint(
            "avoid_start_min IS NULL OR avoid_end_min IS NULL "
            "OR avoid_start_min < avoid_end_min",
            name="ck_preference_avoid_range",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", unique=True)

    # 질문 1이 두 값을 낸다. 자정부터 분 — 540 = 9:00.
    day_start_min: int | None = Field(default=None)
    day_end_min: int | None = Field(default=None)

    # 질문 2.
    mode_pref: Mode | None = enum_text(nullable=True, length=10)

    # 질문 3. 여섯 중 여러 개. 테이블로 빼지 않은 이유는 값이 고정이고
    # 조건 검색을 안 해서다 — Postgres 배열 한 칸으로 끝난다.
    dayparts: list[Daypart] | None = enum_text_array()

    # 질문 4. 사람이 적은 말 그대로.
    avoid_raw: str | None = Field(default=None, max_length=200)
    # 질문 4를 에이전트가 다듬은 문장. 조율 때 이유로 말하는 건 이쪽이다.
    # "금요일 저녁은 피하고 싶어요" → "금요일 저녁은 개인 일정이 있어 어렵습니다"
    # 온보딩 직후 한 번 만들어 저장한다. 조율마다 LLM을 다시 부르지 않는다.
    avoid_polished: str | None = Field(default=None, max_length=200)

    # 같은 한 줄에서 뽑은 요일·시각. **점수에 쓰는 건 이 셋이다**(브리프 11/5).
    #
    # 셋 다 차 있을 때만 쓴다. "너무 이른 시간은 싫어요"처럼 요일이나 범위를
    # 못 뽑는 말이 흔한데, 그때 억지로 숫자를 만들면 엉뚱한 시간이 거절된다.
    # 못 뽑으면 avoid_polished만 남고 점수는 안 건드린다 — 말에는 쓰이니
    # 값이 없는 건 아니다.
    avoid_weekdays: list[int] | None = int_array()
    avoid_start_min: int | None = Field(default=None)
    avoid_end_min: int | None = Field(default=None)

    updated_at: datetime = ts(auto_now=True)


class ScheduleItem(SQLModel, table=True):
    """시간표 한 칸. 수업·알바·약속이 다 여기 들어온다.

    확정된 회의는 넣지 않는다 — meeting에서 읽어 겹친다. 같은 걸 두 곳에
    쓰면 반드시 어긋나는데, 빈칸 찾기가 그걸 제일 먼저 밟는다.
    """

    __tablename__ = "schedule_item"
    __table_args__ = (
        CheckConstraint(in_check("source", ScheduleSource), name="ck_schedule_source"),
        CheckConstraint(in_check("kind", ScheduleKind), name="ck_schedule_kind"),
        CheckConstraint(in_check("recurrence", Recurrence), name="ck_schedule_recur"),
        CheckConstraint(
            "weekday IS NULL OR weekday BETWEEN 0 AND 6", name="ck_schedule_weekday"
        ),
        # weekly는 요일과 분을, once는 시각을 채운다. 반쪽만 채워진 행을 막는다.
        CheckConstraint(
            "(recurrence = 'weekly' AND weekday IS NOT NULL "
            " AND start_min IS NOT NULL AND end_min IS NOT NULL) "
            "OR (recurrence = 'once' AND start_at IS NOT NULL AND end_at IS NOT NULL)",
            name="ck_schedule_shape",
        ),
        CheckConstraint(
            "start_min IS NULL OR end_min IS NULL OR start_min < end_min",
            name="ck_schedule_min_range",
        ),
        CheckConstraint(
            "start_at IS NULL OR end_at IS NULL OR start_at < end_at",
            name="ck_schedule_at_range",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)

    # 같은 값을 가진 행들이 "묶인 일정" 하나다. 월 9시·수 11시인 수업 하나는
    # 요일별 시간이 달라서 한 행에 담을 수 없다 — 명세의
    # PUT /me/schedule/groups/{id}가 "요일마다 다른 시간"이라고 적었다.
    group_id: int | None = Field(default=None, index=True)

    source: ScheduleSource = enum_text(length=10)
    kind: ScheduleKind = enum_text(length=12)
    # appointment는 비운다. 화면에 "바쁨"으로만 나간다 —
    # 구글 캘린더에서 온 개인 약속의 제목을 팀원에게 보여 주지 않는다.
    title: str | None = Field(default=None, max_length=60)

    recurrence: Recurrence = enum_text(length=8)

    # recurrence = weekly일 때
    weekday: int | None = Field(default=None)  # 0=월 … 6=일. 에브리타임과 같다.
    start_min: int | None = Field(default=None)  # 자정부터 분
    end_min: int | None = Field(default=None)
    valid_from: date | None = Field(default=None)  # 학기 범위
    valid_to: date | None = Field(default=None)

    # recurrence = once일 때
    start_at: datetime | None = ts(nullable=True)
    end_at: datetime | None = ts(nullable=True)

    created_at: datetime = ts(auto_now=True)
