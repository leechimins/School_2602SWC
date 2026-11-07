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

from fastapi import APIRouter, Depends
from sqlmodel import Field, Session, SQLModel, col, select

from app.me.models import ScheduleItem
from app.meeting.models import Meeting, MeetingResponse
from app.meeting.slots import expand_busy
from app.shared import demo_clock
from app.shared.auth import current_user_id, require_member
from app.shared.base import KST
from app.shared.db import session_dep
from app.shared.enums import MeetingStatus, ResponseState, ScheduleKind, ScheduleSource

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
