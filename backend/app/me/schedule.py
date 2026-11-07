"""주간 시간표 — GET /rooms/{room_id}/me/schedule.

마이페이지에서 "내 시간표"를 한 주 단위로 본다. 브리프: 수업 / 일정 / 팀 회의를
구분하고, 알바·캘린더 약속은 "일정" 하나로 묶는다(11/4).

**내 것만 나간다.** 남의 시간표는 조율이 점수로만 쓰고 화면에는 안 보인다. 내 일정은
본인 것이라 제목까지 보여 준다 — 제목이 없는 약속(구글에서 온 것)은 null이고 화면이
"약속"으로 그린다.

매주 반복·학기 범위·일회성을 펼치는 일은 조율이 이미 하고 있다(meeting/slots.py의
expand_busy). 그걸 그대로 쓴다 — 두 번 짜면 조율이 막힌 시간으로 보는 것과 시간표에
보이는 것이 어긋난다.

방 주소 밑에 있는 이유: 팀 회의가 방마다 다르다. 내 일정은 방과 상관없이 같다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Field, Session, SQLModel, col, func, select

from app.me.models import ScheduleItem
from app.meeting.models import Meeting, MeetingResponse
from app.meeting.slots import expand_busy
from app.shared import demo_clock
from app.shared.auth import current_user_id, require_member
from app.shared.base import KST
from app.shared.db import session_dep
from app.shared.enums import (
    MeetingStatus,
    Recurrence,
    ResponseState,
    ScheduleKind,
    ScheduleSource,
)

router = APIRouter(prefix="/rooms/{room_id}/me", tags=["me"])

Kind = Literal["class", "event", "meeting"]


class MyScheduleItemOut(SQLModel):
    kind: Kind = Field(description="class 수업 · event 일정(알바·약속) · meeting 팀 회의")
    title: str | None = Field(description="제목. 제목 없는 약속(구글에서 온 것)은 null")
    start_at: datetime
    end_at: datetime
    source: ScheduleSource | None = Field(
        description="어디서 왔나(everytime·google·manual). 팀 회의는 null"
    )
    item_id: int | None = Field(description="내 일정이면 그 일정 ID(고치기·지우기용)")
    meeting_id: int | None = Field(description="팀 회의면 그 회의 ID")
    meeting_status: MeetingStatus | None = Field(
        description="팀 회의의 상태. proposed면 아직 확정 대기"
    )


class MyScheduleOut(SQLModel):
    week_start: date = Field(description="그 주 월요일")
    week_end: date = Field(description="그 주 일요일")
    items: list[MyScheduleItemOut] = Field(description="시작 순")


# 수업은 수업, 나머지(알바·약속)는 "일정" 하나로(브리프 11/4)
_KIND: dict[str, Kind] = {
    ScheduleKind.CLASS: "class",
    ScheduleKind.PARTTIME: "event",
    ScheduleKind.APPOINTMENT: "event",
}


@router.get("/schedule", response_model=MyScheduleOut)
def my_schedule(
    room_id: int,
    week: date | None = None,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> MyScheduleOut:
    """한 주(월~일)의 내 시간표.

    week는 그 주의 아무 날이나 된다. 안 주면 시연 시계 기준 이번 주 — 시연에서
    날짜를 옮기면 시간표도 따라간다.
    """
    require_member(db, room_id, user_id)

    day = week or demo_clock.now(db).date()
    monday = day - timedelta(days=day.weekday())
    start = datetime.combine(monday, datetime.min.time(), tzinfo=KST)
    end = start + timedelta(days=7)

    items: list[MyScheduleItemOut] = []

    mine = db.exec(select(ScheduleItem).where(ScheduleItem.user_id == user_id)).all()
    for item in mine:
        # 일정 하나씩 펼친다. 펼친 결과(Busy)에는 어느 일정에서 왔는지가 없어서다
        for busy in expand_busy([item], start, end):
            items.append(
                MyScheduleItemOut(
                    kind=_KIND.get(item.kind, "event"),
                    title=item.title,
                    start_at=busy.start_at,
                    end_at=busy.end_at,
                    source=item.source,
                    item_id=item.id,
                    meeting_id=None,
                    meeting_status=None,
                )
            )

    # 팀 회의: 내가 응답자이고 거절하지 않은 것. 응답 행이 없으면 빠지는 사람이다
    meetings = db.exec(
        select(Meeting)
        .join(MeetingResponse, col(MeetingResponse.meeting_id) == col(Meeting.id))
        .where(
            Meeting.room_id == room_id,
            col(Meeting.status).in_(
                [MeetingStatus.PROPOSED, MeetingStatus.CONFIRMED, MeetingStatus.DONE]
            ),
            Meeting.start_at < end,
            Meeting.end_at > start,
            MeetingResponse.user_id == user_id,
            MeetingResponse.state != ResponseState.DECLINED,
        )
    ).all()
    for meeting in meetings:
        items.append(
            MyScheduleItemOut(
                kind="meeting",
                title=meeting.topic,
                start_at=meeting.start_at,
                end_at=meeting.end_at,
                source=None,
                item_id=None,
                meeting_id=meeting.id,
                meeting_status=meeting.status,
            )
        )

    items.sort(key=lambda i: i.start_at)
    return MyScheduleOut(
        week_start=monday, week_end=monday + timedelta(days=6), items=items
    )


# ── 일정 직접 추가 ───────────────────────────────────────────────────
# 목업 "일정 추가" 화면(docs/mockup/index.html blkForm)이 받는 그대로다: 이름 · 종류
# (수업/일정) · 요일 여러 개 · 요일마다 시간. 매주 반복만 받는다.

items_router = APIRouter(prefix="/me/schedule", tags=["me"])

# 화면의 두 종류 → 저장하는 종류. "일정"은 약속으로 둔다 — 조율 발언에서 "일정이
# 있습니다"가 된다(meeting/slots.py _label).
_STORE_KIND: dict[str, ScheduleKind] = {
    "class": ScheduleKind.CLASS,
    "event": ScheduleKind.APPOINTMENT,
}

_WEEKDAY_NAMES = "월화수목금토일"


class DayIn(SQLModel):
    weekday: int = Field(ge=0, le=6, description="0=월 … 6=일")
    start_min: int = Field(ge=0, le=1440, description="자정부터 분. 18:00 = 1080")
    end_min: int = Field(ge=0, le=1440, description="자정부터 분")


class ScheduleItemsIn(SQLModel):
    title: str = Field(min_length=1, max_length=20, description="이름. 나만 보인다")
    kind: Literal["class", "event"] = Field(description="class 수업 · event 일정")
    days: list[DayIn] = Field(min_length=1, max_length=7, description="요일마다 시간")


class DayOut(SQLModel):
    id: int
    weekday: int
    start_min: int
    end_min: int


class ScheduleItemsOut(SQLModel):
    group_id: int = Field(description="이 묶음. 요일마다 한 줄이 같은 묶음이다")
    title: str
    kind: Literal["class", "event"]
    days: list[DayOut]


def _invalid(message: str) -> HTTPException:
    return HTTPException(
        status.HTTP_400_BAD_REQUEST,
        detail={"code": "INVALID_INPUT", "field": "days", "message": message},
    )


def _class_conflict(db: Session, user_id: int, days: list[DayIn]) -> bool:
    """넣으려는 요일·시간이 내 수업과 겹치는지. 붙어 있는 건 겹침이 아니다.

    이미 끝난 학기의 수업은 안 센다 — 지난 학기 시간표가 남아 있어도 새 일정을
    막으면 안 된다.
    """
    today = demo_clock.now(db).date()
    classes = db.exec(
        select(ScheduleItem).where(
            ScheduleItem.user_id == user_id,
            ScheduleItem.kind == ScheduleKind.CLASS,
            ScheduleItem.recurrence == Recurrence.WEEKLY,
        )
    ).all()
    for c in classes:
        if c.valid_to is not None and c.valid_to < today:
            continue
        for d in days:
            if (
                c.weekday == d.weekday
                and c.start_min is not None
                and c.end_min is not None
                and d.start_min < c.end_min
                and c.start_min < d.end_min
            ):
                return True
    return False


@items_router.post(
    "/items", response_model=ScheduleItemsOut, status_code=status.HTTP_201_CREATED
)
def add_schedule_items(
    body: ScheduleItemsIn,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> ScheduleItemsOut:
    """일정 한 묶음을 넣는다. 요일마다 한 줄이고 같은 group_id로 묶인다.

    **다 넣거나 하나도 안 넣는다.** 검사를 다 통과한 뒤에만 넣고 한 번에 커밋한다.

    이미 있는 **수업과 겹치면 409** "이미 수업이 있습니다." — 같은 시간에 두 일을 넣으면
    시간표가 틀리고, 수업은 에브리타임에서 오는 고정된 시간이라 그쪽이 맞다.

    이미 도는 조율에는 안 들어간다. 조율은 열 때 점수를 저장하므로 다음 조율부터다.
    """
    seen: set[int] = set()
    for d in body.days:
        if d.weekday in seen:
            raise _invalid(f"{_WEEKDAY_NAMES[d.weekday]}요일이 두 번 들어 있어요.")
        seen.add(d.weekday)
        if d.start_min >= d.end_min:
            raise _invalid("시작 시각이 끝 시각보다 앞이어야 해요.")

    if _class_conflict(db, user_id, body.days):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "CLASS_CONFLICT", "field": "days", "message": "이미 수업이 있습니다."},
        )

    # 묶음 번호는 내 묶음 중 가장 큰 것 + 1. 첫 줄의 id를 쓰지 않는 이유: 시드가
    # group_id를 101 같은 고정값으로 넣어 두어서, 새 id가 그 수에 닿으면 섞인다.
    group_id = (
        db.exec(
            select(func.max(ScheduleItem.group_id)).where(ScheduleItem.user_id == user_id)
        ).one()
        or 0
    ) + 1

    rows = [
        ScheduleItem(
            user_id=user_id,
            group_id=group_id,
            source=ScheduleSource.MANUAL,
            kind=_STORE_KIND[body.kind],
            title=body.title.strip(),
            recurrence=Recurrence.WEEKLY,
            weekday=d.weekday,
            start_min=d.start_min,
            end_min=d.end_min,
        )
        for d in sorted(body.days, key=lambda d: d.weekday)
    ]
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)

    return ScheduleItemsOut(
        group_id=group_id,
        title=body.title.strip(),
        kind=body.kind,
        days=[
            DayOut(id=r.id, weekday=r.weekday, start_min=r.start_min, end_min=r.end_min)  # type: ignore[arg-type]
            for r in rows
        ],
    )
