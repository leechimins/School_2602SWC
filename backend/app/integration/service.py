"""외부 연동 — 구글 캘린더 약속을 "바쁨"으로 시간표에 넣는다. 레인 B.

연동은 선택이다. 연결 안 해도, 실패해도 직접 입력으로 모든 화면이 돈다.

- 구글 약속은 schedule_item(source=google, appointment, once, 제목 없음)이 된다.
  제목을 비우면 조율 화면(meeting/slots._label)이 "바쁨"으로 그린다.
- 동기화는 "이전 구글 약속을 지우고 새로 넣기"다. 구글에서 지운 약속이
  남지 않게 하려면 이게 제일 단순하다. 직접 입력·에브리타임 행은 안 건드린다.
- 실패하면 이전 구글 약속을 그대로 둔다. 빈 시간표보다 조금 낡은 시간표가 낫다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import delete, func
from sqlmodel import Session, select

from app.integration import google_calendar as google
from app.me.models import ScheduleItem
from app.minutes.models import CalendarLink
from app.shared import demo_clock
from app.shared.base import KST, real_now
from app.shared.enums import (
    CalendarKind,
    LinkStatus,
    Recurrence,
    ScheduleKind,
    ScheduleSource,
)

# 오늘부터 몇 주를 읽나. 시연일(11/10)에서 마감(12/11)까지 덮는다.
SYNC_WEEKS = 5


@dataclass(frozen=True)
class Busy:
    start_at: datetime
    end_at: datetime


class ReconnectNeeded(Exception):
    """갱신 토큰까지 막혔다. status를 failed로 두고 다시 연결하게 한다."""


def _day_start(value: str) -> datetime:
    return datetime.combine(date.fromisoformat(value), time(0), tzinfo=KST)


def _declined(event: dict) -> bool:
    return any(
        a.get("self") and a.get("responseStatus") == "declined"
        for a in event.get("attendees", [])
    )


def to_busy(events: list[dict]) -> list[Busy]:
    """구글 약속 → 바쁜 구간. 제목·장소·참석자는 여기서 버린다.

    - 시간 있는 약속: "한가함"으로 표시한 것(transparency=transparent)은 뺀다.
    - 종일 일정: 시작일 00:00 ~ 끝날 00:00 한 구간. 구글은 종일 일정을 기본으로
      "한가함"으로 두므로 transparency를 보지 않는다 — 여행처럼 정말 막히는
      날을 놓치지 않으려는 것. 공휴일·생일은 기본 캘린더가 아니라 안 섞인다.
    - 취소된 약속, 내가 거절한 약속은 뺀다.
    """
    busy: list[Busy] = []
    for event in events:
        if event.get("status") == "cancelled" or _declined(event):
            continue
        start, end = event.get("start", {}), event.get("end", {})
        if "dateTime" in start and "dateTime" in end:
            if event.get("transparency") == "transparent":
                continue
            start_at = datetime.fromisoformat(start["dateTime"]).astimezone(KST)
            end_at = datetime.fromisoformat(end["dateTime"]).astimezone(KST)
        elif "date" in start and "date" in end:
            start_at, end_at = _day_start(start["date"]), _day_start(end["date"])
        else:
            continue
        # CHECK(start_at < end_at)에 걸리는 0분짜리 약속은 막는 시간이 없다.
        if start_at < end_at:
            busy.append(Busy(start_at, end_at))
    return busy


def get_link(db: Session, user_id: int, *, lock: bool = False) -> CalendarLink | None:
    query = select(CalendarLink).where(
        CalendarLink.user_id == user_id, CalendarLink.kind == CalendarKind.GOOGLE
    )
    if lock:
        # 동기화 두 번이 겹치면 둘 다 지우고 둘 다 넣어 약속이 두 벌이 된다.
        query = query.with_for_update()
    return db.exec(query).first()


def imported_count(db: Session, user_id: int) -> int:
    return db.exec(
        select(func.count())
        .select_from(ScheduleItem)
        .where(
            ScheduleItem.user_id == user_id,
            ScheduleItem.source == ScheduleSource.GOOGLE,
        )
    ).one()


def _remove_items(db: Session, user_id: int) -> None:
    db.execute(
        delete(ScheduleItem).where(
            ScheduleItem.user_id == user_id,
            ScheduleItem.source == ScheduleSource.GOOGLE,
        )
    )


def _fetch(db: Session, link: CalendarLink) -> list[dict]:
    """약속을 읽는다. 접근 토큰이 만료됐으면 한 번 갱신하고 다시 읽는다.

    만료 시각을 저장하지 않는다. 401을 받으면 갱신하는 쪽이 칸 하나 덜 쓰고,
    시계를 옮기는 시연에서도 어긋나지 않는다.
    """
    today = demo_clock.now(db)
    start = datetime.combine(today.date(), time(0), tzinfo=KST)
    end = start + timedelta(weeks=SYNC_WEEKS)
    try:
        return google.list_events(link.access_token or "", start, end)
    except google.Unauthorized:
        pass
    if not link.refresh_token:
        raise ReconnectNeeded
    try:
        link.access_token = google.refresh(link.refresh_token)
    except google.InvalidGrant:
        raise ReconnectNeeded from None
    db.add(link)
    try:
        return google.list_events(link.access_token, start, end)
    except (google.Unauthorized, google.InvalidGrant):
        raise ReconnectNeeded from None


def sync(db: Session, link: CalendarLink) -> None:
    """약속을 읽어 구글 행을 통째로 바꾼다. 커밋은 부르는 쪽이 한다.

    ReconnectNeeded면 link.status를 failed로 바꾸고 다시 올린다(행은 그대로).
    google.Unavailable은 아무것도 안 바꾸고 그대로 올린다.
    """
    try:
        events = _fetch(db, link)
    except (ReconnectNeeded, google.InvalidGrant):
        link.status = LinkStatus.FAILED
        db.add(link)
        raise ReconnectNeeded from None

    _remove_items(db, link.user_id)
    for item in to_busy(events):
        db.add(
            ScheduleItem(
                user_id=link.user_id,
                source=ScheduleSource.GOOGLE,
                kind=ScheduleKind.APPOINTMENT,
                title=None,
                recurrence=Recurrence.ONCE,
                start_at=item.start_at,
                end_at=item.end_at,
            )
        )
    link.status = LinkStatus.OK
    # 기록용 시각이라 시연 시계가 아니라 실제 시각이다(created_at과 같다).
    link.last_synced_at = real_now()
    db.add(link)


def connect(db: Session, user_id: int, code: str) -> CalendarLink:
    """코드를 토큰으로 바꾸고 연결 행을 만들거나 고친다. 커밋은 부르는 쪽.

    google.InvalidGrant(코드가 잘못됨)·Unavailable은 그대로 올린다.
    """
    tokens = google.exchange_code(code)
    account = google.primary_account(tokens.access_token)

    link = get_link(db, user_id, lock=True)
    if link is None:
        link = CalendarLink(
            user_id=user_id,
            kind=CalendarKind.GOOGLE,
            external_ref=account,
            status=LinkStatus.OK,
        )
    link.external_ref = account[:200]
    link.access_token = tokens.access_token
    # 다시 연결할 때 구글이 갱신 토큰을 안 주면 있던 것을 지킨다.
    if tokens.refresh_token:
        link.refresh_token = tokens.refresh_token
    link.status = LinkStatus.OK
    db.add(link)
    db.flush()
    return link


def disconnect(db: Session, user_id: int) -> None:
    """연결 행과 구글에서 들어온 약속을 지운다. 없어도 조용히 끝난다."""
    link = get_link(db, user_id, lock=True)
    if link is not None:
        db.delete(link)
    _remove_items(db, user_id)
