"""외부 연동 — 구글 캘린더 약속을 "바쁨"으로 시간표에 넣는다. 레인 B.

연동은 선택이다. 연결 안 해도, 실패해도 직접 입력으로 모든 화면이 돈다.

- 구글 약속은 schedule_item(source=google, appointment, once)이 된다. 제목은 남기지만
  본인 일정 화면(GET /me/schedule)에만 나간다. 조율(meeting/slots._label)은 종류만 쓴다.
- 언제 읽나: 연결·동기화 때 오늘부터 팀플 마감일까지(내 화면용), 그리고 팀장이 조율을
  시작할 때 그 조율 기간만 새로(refresh_for_window). 구글에서 고친 약속이 조율에 반영된다.
- 동기화는 "이전 구글 약속을 지우고 새로 넣기"다. 구글에서 지운 약속이
  남지 않게 하려면 이게 제일 단순하다. 직접 입력·에브리타임 행은 안 건드린다.
- 실패하면 이전 구글 약속을 그대로 둔다. 빈 시간표보다 조금 낡은 시간표가 낫다.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import delete, func
from sqlmodel import Session, select

from app.integration import google_calendar as google
from app.me.models import ScheduleItem
from app.minutes.models import CalendarLink
from app.shared import demo_clock
from app.shared.base import KST, real_now
from app.shared.models import Membership, Room
from app.shared.enums import (
    CalendarKind,
    LinkStatus,
    Recurrence,
    ScheduleKind,
    ScheduleSource,
)

log = logging.getLogger(__name__)

# 연결·동기화 때 읽는 기간의 대체값. 보통은 내 팀플 마감일까지 읽고, 방이 없거나
# 마감이 지났을 때만 오늘부터 이만큼 읽는다.
SYNC_WEEKS = 5
# 조율 시작 때 구글을 기다리는 시간(팀원 전체를 동시에). 화면이 조율 시작 응답을
# 5초까지만 기다려서 그 안에 끝나야 한다. 넘으면 그 사람은 저장된 약속으로 간다.
REFRESH_BUDGET_SEC = 3.0
TITLE_MAX = 60  # ScheduleItem.title 길이


@dataclass(frozen=True)
class Busy:
    start_at: datetime
    end_at: datetime
    title: str | None = None  # 본인 화면에만 나간다


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
    """구글 약속 → 바쁜 구간. 장소·참석자는 버리고, 제목은 본인 화면용으로 남긴다.

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
            title = (event.get("summary") or "").strip()[:TITLE_MAX] or None
            busy.append(Busy(start_at, end_at, title))
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


def _remove_items(
    db: Session, user_id: int, start: datetime | None = None, end: datetime | None = None
) -> None:
    """구글 행을 지운다. 기간을 주면 그 기간에 걸친 것만 지운다(밖의 행은 내 화면용으로 남긴다)."""
    query = delete(ScheduleItem).where(
        ScheduleItem.user_id == user_id,
        ScheduleItem.source == ScheduleSource.GOOGLE,
    )
    if start is not None and end is not None:
        query = query.where(ScheduleItem.start_at < end, ScheduleItem.end_at > start)  # type: ignore[operator]
    db.execute(query)


def _default_window(db: Session, user_id: int) -> tuple[datetime, datetime]:
    """연결·동기화 때 읽는 기간: 오늘부터 내 팀플 마감일 다음 날 00:00까지.

    방이 여럿이면 가장 늦은 마감. 방이 없거나 마감이 지났으면 오늘부터 SYNC_WEEKS주.
    """
    today = demo_clock.now(db).date()
    start = datetime.combine(today, time(0), tzinfo=KST)
    due = db.exec(
        select(func.max(Room.due_date))
        .join(Membership, Membership.room_id == Room.id)  # type: ignore[arg-type]
        .where(Membership.user_id == user_id)
    ).one()
    if due is None or due < today:
        return start, start + timedelta(weeks=SYNC_WEEKS)
    return start, datetime.combine(due + timedelta(days=1), time(0), tzinfo=KST)


def _read(
    access_token: str | None, refresh_token: str | None, start: datetime, end: datetime
) -> tuple[list[dict], str | None]:
    """구글에서 약속을 읽는다. DB를 안 만져서 스레드에서 불러도 된다.

    접근 토큰이 만료(401)면 한 번 갱신해서 다시 읽는다. 두 번째 값은 새 접근 토큰
    (갱신했을 때만) — 저장은 부르는 쪽이 한다. 만료 시각을 저장하지 않는다. 401을
    받으면 갱신하는 쪽이 칸 하나 덜 쓰고, 시계를 옮기는 시연에서도 어긋나지 않는다.
    """
    try:
        return google.list_events(access_token or "", start, end), None
    except google.Unauthorized:
        pass
    if not refresh_token:
        raise ReconnectNeeded
    try:
        fresh = google.refresh(refresh_token)
    except google.InvalidGrant:
        raise ReconnectNeeded from None
    try:
        return google.list_events(fresh, start, end), fresh
    except (google.Unauthorized, google.InvalidGrant):
        raise ReconnectNeeded from None


def _store(
    db: Session,
    link: CalendarLink,
    events: list[dict],
    start: datetime | None = None,
    end: datetime | None = None,
) -> None:
    """읽은 약속으로 구글 행을 바꾼다. 기간을 주면 그 기간 안만."""
    _remove_items(db, link.user_id, start, end)
    for item in to_busy(events):
        db.add(
            ScheduleItem(
                user_id=link.user_id,
                source=ScheduleSource.GOOGLE,
                kind=ScheduleKind.APPOINTMENT,
                title=item.title,
                recurrence=Recurrence.ONCE,
                start_at=item.start_at,
                end_at=item.end_at,
            )
        )
    link.status = LinkStatus.OK
    # 기록용 시각이라 시연 시계가 아니라 실제 시각이다(created_at과 같다).
    link.last_synced_at = real_now()
    db.add(link)


def _mark_failed(db: Session, link: CalendarLink) -> None:
    link.status = LinkStatus.FAILED
    db.add(link)


def sync(db: Session, link: CalendarLink) -> None:
    """오늘부터 팀플 마감일까지 읽어 구글 행을 통째로 바꾼다. 커밋은 부르는 쪽이 한다.

    ReconnectNeeded면 link.status를 failed로 바꾸고 다시 올린다(행은 그대로).
    google.Unavailable은 아무것도 안 바꾸고 그대로 올린다.
    """
    start, end = _default_window(db, link.user_id)
    try:
        events, fresh = _read(link.access_token, link.refresh_token, start, end)
    except (ReconnectNeeded, google.InvalidGrant):
        _mark_failed(db, link)
        raise ReconnectNeeded from None
    if fresh:
        link.access_token = fresh
    _store(db, link, events)


def refresh_for_window(
    db: Session, user_ids: Sequence[int], start: datetime, end: datetime
) -> None:
    """조율 시작 때: 연결된 팀원들의 그 기간 약속을 구글에서 새로 읽어 바꾼다. 커밋은 부르는 쪽.

    조율을 막지 않는다. 구글이 늦거나(REFRESH_BUDGET_SEC) 실패하면 그 사람은 저장된 약속
    그대로 간다. 권한이 끊겼으면 status만 failed로 둔다. 구글 호출만 스레드에서 하고
    DB는 이 스레드에서만 만진다(세션은 스레드끼리 나눠 쓸 수 없다).
    """
    if not user_ids or not google.configured():
        return
    links = list(
        db.exec(
            select(CalendarLink)
            .where(
                CalendarLink.user_id.in_(user_ids),  # type: ignore[attr-defined]
                CalendarLink.kind == CalendarKind.GOOGLE,
                CalendarLink.status == LinkStatus.OK,
            )
            # 그 사람이 지금 동기화 중이면 건너뛴다. 기다리면 조율 시작이 늦어진다.
            .with_for_update(skip_locked=True)
        )
    )
    if not links:
        return
    pool = ThreadPoolExecutor(max_workers=len(links))
    futures = {
        pool.submit(_read, link.access_token, link.refresh_token, start, end): link
        for link in links
    }
    done, _ = wait(futures, timeout=REFRESH_BUDGET_SEC)
    # 늦은 호출은 기다리지 않는다. 그 스레드는 구글 제한 시간이 지나면 혼자 끝난다.
    pool.shutdown(wait=False, cancel_futures=True)
    for future in done:
        link = futures[future]
        try:
            events, fresh = future.result()
        except (ReconnectNeeded, google.InvalidGrant):
            _mark_failed(db, link)
            continue
        except Exception as exc:  # noqa: BLE001 - 무엇이든 조율은 저장된 약속으로 이어 간다
            log.warning("조율 전 구글 읽기 실패(user %s): %s", link.user_id, type(exc).__name__)
            continue
        if fresh:
            link.access_token = fresh
        _store(db, link, events, start, end)


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
