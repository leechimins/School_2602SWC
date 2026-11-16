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

from fastapi import APIRouter, Depends, HTTPException, Response, status
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
    recurrence: Recurrence | None = Field(
        default=None, description="weekly 매주 반복 · once 한 번만. 팀 회의는 null"
    )
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
                    recurrence=item.recurrence,
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


# ── 일정 직접 추가·고치기·지우기 ─────────────────────────────────────
# 매주 반복: 이름 · 종류(수업/일정) · 요일 여러 개 · 요일마다 시간(목업 blkForm 그대로).
# 한 번만: 이름 · 시작·끝 시각(같은 날). 시간은 30분 단위다.

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
    recurrence: Literal["weekly", "once"] = Field(
        default="weekly", description="weekly 매주 반복(days) · once 한 번만(start_at·end_at)"
    )
    title: str = Field(min_length=1, max_length=20, description="이름. 나만 보인다")
    kind: Literal["class", "event"] = Field(
        default="event", description="class 수업 · event 일정. 한 번만은 늘 일정"
    )
    days: list[DayIn] = Field(default=[], max_length=7, description="weekly: 요일마다 시간")
    start_at: datetime | None = Field(default=None, description="once: 시작(+09:00 붙여서)")
    end_at: datetime | None = Field(default=None, description="once: 끝. 같은 날, 24:00까지")


class ScheduleItemPatch(SQLModel):
    """직접 넣은 일정 한 칸 고치기. 보낸 것만 바꾼다. 매주 반복은 그 요일 한 칸, 한 번만은 같은 날 안에서."""

    title: str | None = Field(default=None, min_length=1, max_length=20)
    start_min: int | None = Field(default=None, ge=0, le=1440)
    end_min: int | None = Field(default=None, ge=0, le=1440)


class DayOut(SQLModel):
    id: int
    weekday: int
    start_min: int
    end_min: int


class ScheduleItemsOut(SQLModel):
    recurrence: Literal["weekly", "once"] = "weekly"
    group_id: int | None = Field(description="weekly: 이 묶음. 요일마다 한 줄이 같은 묶음이다")
    title: str
    kind: Literal["class", "event"]
    days: list[DayOut] = []
    item_id: int | None = Field(default=None, description="once: 넣은 일정 ID")
    start_at: datetime | None = None
    end_at: datetime | None = None


def _invalid(message: str, field: str = "days") -> HTTPException:
    return HTTPException(
        status.HTTP_400_BAD_REQUEST,
        detail={"code": "INVALID_INPUT", "field": field, "message": message},
    )


def _class_conflict(
    db: Session,
    user_id: int,
    days: list[DayIn],
    on: date | None = None,
    skip_id: int | None = None,
) -> bool:
    """넣으려는 요일·시간이 내 수업과 겹치는지. 붙어 있는 건 겹침이 아니다.

    이미 끝난 학기의 수업은 안 센다 — 지난 학기 시간표가 남아 있어도 새 일정을
    막으면 안 된다. on(한 번만 일정의 날짜)을 주면 그날 학기 안인 수업만 본다.
    skip_id는 고치는 그 칸 자신(수업을 고칠 때 자기와 겹친다고 막지 않게).
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
        if c.id == skip_id:
            continue
        if c.valid_to is not None and c.valid_to < (on or today):
            continue
        if on is not None and c.valid_from is not None and on < c.valid_from:
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

    recurrence=once면 start_at·end_at 하나(같은 날, 30분 단위, 지난 시각은 안 됨).
    """
    if body.recurrence == "once":
        return _add_once(db, user_id, body)
    if not body.days:
        raise _invalid("요일을 하나는 골라 주세요.")
    seen: set[int] = set()
    for d in body.days:
        if d.weekday in seen:
            raise _invalid(f"{_WEEKDAY_NAMES[d.weekday]}요일이 두 번 들어 있어요.")
        seen.add(d.weekday)
        _check_minutes(d.start_min, d.end_min)

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


def _check_minutes(start_min: int, end_min: int, field: str = "days") -> None:
    if start_min >= end_min:
        raise _invalid("시작 시각이 끝 시각보다 앞이어야 해요.", field)
    if start_min % 30 or end_min % 30:
        raise _invalid("시간은 30분 단위로 골라 주세요.", field)


def _conflict() -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        detail={"code": "CLASS_CONFLICT", "field": "days", "message": "이미 수업이 있습니다."},
    )


def _day_minutes(start_at: datetime, end_at: datetime) -> tuple[date, int, int]:
    """한 번만 일정을 (날짜, 시작 분, 끝 분)으로. 끝이 다음 날 00:00이면 1440분이다."""
    start = start_at.astimezone(KST)
    end = end_at.astimezone(KST)
    day = start.date()
    midnight = datetime.combine(day, datetime.min.time(), tzinfo=KST)
    return day, int((start - midnight).total_seconds() // 60), int((end - midnight).total_seconds() // 60)


def _at(day: date, minute: int) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=KST) + timedelta(minutes=minute)


def _add_once(db: Session, user_id: int, body: ScheduleItemsIn) -> ScheduleItemsOut:
    if body.start_at is None or body.end_at is None:
        raise _invalid("한 번만 일정은 시작과 끝 시각이 있어야 해요.", "start_at")
    if body.start_at.tzinfo is None or body.end_at.tzinfo is None:
        raise _invalid("시각에 +09:00을 붙여 보내 주세요.", "start_at")
    day, start_min, end_min = _day_minutes(body.start_at, body.end_at)
    if end_min > 1440:
        raise _invalid("한 번만 일정은 하루 안에서 끝나야 해요.", "end_at")
    _check_minutes(start_min, end_min, "start_at")
    start_at = _at(day, start_min)
    if start_at < demo_clock.now(db):
        raise _invalid("지난 시간에는 넣을 수 없어요.", "start_at")
    if _class_conflict(db, user_id, [DayIn(weekday=day.weekday(), start_min=start_min, end_min=end_min)], on=day):
        raise _conflict()

    row = ScheduleItem(
        user_id=user_id,
        source=ScheduleSource.MANUAL,
        kind=ScheduleKind.APPOINTMENT,
        title=body.title.strip(),
        recurrence=Recurrence.ONCE,
        start_at=start_at,
        end_at=_at(day, end_min),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ScheduleItemsOut(
        recurrence="once",
        group_id=None,
        title=row.title or "",
        kind="event",
        item_id=row.id,
        start_at=row.start_at,
        end_at=row.end_at,
    )


def _my_manual_item(db: Session, user_id: int, item_id: int) -> ScheduleItem:
    """내가 직접 넣은 일정 한 칸. 남의 것·없는 것은 404, 연동해 온 것은 409."""
    item = db.get(ScheduleItem, item_id)
    if item is None or item.user_id != user_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "그 일정을 찾을 수 없어요."},
        )
    if item.source != ScheduleSource.MANUAL:
        where = "구글 캘린더" if item.source == ScheduleSource.GOOGLE else "에브리타임"
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "LINKED_ITEM", "message": f"{where}에서 가져온 일정은 {where}에서 고쳐 주세요."},
        )
    return item


@items_router.patch("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def edit_schedule_item(
    item_id: int,
    body: ScheduleItemPatch,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> Response:
    """직접 넣은 일정 한 칸(매주 반복은 그 요일 하나)의 이름·시간을 고친다.

    - 남의 것·없는 것은 404 `NOT_FOUND`, 구글·에브리타임에서 온 것은 409 `LINKED_ITEM`
    - 시간 규칙은 추가와 같다(시작 < 끝, 30분 단위). 수업과 겹치면 409 `CLASS_CONFLICT`
    - 한 번만 일정은 같은 날 안에서 시각만 바뀐다
    """
    item = _my_manual_item(db, user_id, item_id)

    if item.recurrence == Recurrence.WEEKLY:
        start_min = body.start_min if body.start_min is not None else item.start_min
        end_min = body.end_min if body.end_min is not None else item.end_min
        assert start_min is not None and end_min is not None and item.weekday is not None
        _check_minutes(start_min, end_min, "start_min")
        day_in = DayIn(weekday=item.weekday, start_min=start_min, end_min=end_min)
        if _class_conflict(db, user_id, [day_in], skip_id=item.id):
            raise _conflict()
        item.start_min, item.end_min = start_min, end_min
    else:
        assert item.start_at is not None and item.end_at is not None
        day, old_start, old_end = _day_minutes(item.start_at, item.end_at)
        start_min = body.start_min if body.start_min is not None else old_start
        end_min = body.end_min if body.end_min is not None else old_end
        _check_minutes(start_min, end_min, "start_min")
        day_in = DayIn(weekday=day.weekday(), start_min=start_min, end_min=end_min)
        if _class_conflict(db, user_id, [day_in], on=day, skip_id=item.id):
            raise _conflict()
        item.start_at, item.end_at = _at(day, start_min), _at(day, end_min)

    if body.title is not None:
        item.title = body.title.strip() or item.title
    db.add(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@items_router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule_item(
    item_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> Response:
    """직접 넣은 일정 한 칸을 지운다. 매주 반복은 그 요일 하나만(같은 묶음의 다른 요일은 남는다).

    권한 규칙은 고치기와 같다(404 `NOT_FOUND` · 409 `LINKED_ITEM`).
    """
    item = _my_manual_item(db, user_id, item_id)
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
