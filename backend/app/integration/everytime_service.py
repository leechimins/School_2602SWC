"""에브리타임 연결·끊기. 레인 B.

연동은 선택이다. 연결 안 해도, 실패해도 직접 입력으로 모든 화면이 돈다.

- 연결 = 시간표 읽기. 이미 연결돼 있으면 같은 요청이 "다시 불러오기"다.
- 실패하면 이전 수업을 그대로 둔다(빈 시간표보다 조금 낡은 시간표가 낫다).
  연결돼 있던 사람이면 status만 failed로 바꾼다.
- 수업을 어떻게 넣는지는 timetable.py, 어떻게 읽는지는 everytime.py.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlmodel import Session, select

from app.integration import everytime
from app.integration import timetable as tt
from app.minutes.models import CalendarLink
from app.shared.base import real_now
from app.shared.enums import CalendarKind, LinkStatus


def get_link(db: Session, user_id: int, *, lock: bool = False) -> CalendarLink | None:
    query = select(CalendarLink).where(
        CalendarLink.user_id == user_id, CalendarLink.kind == CalendarKind.EVERYTIME
    )
    if lock:
        # 불러오기 두 번이 겹치면 둘 다 지우고 둘 다 넣어 수업이 두 벌이 된다.
        query = query.with_for_update()
    return db.exec(query).first()


def connect(
    db: Session,
    user_id: int,
    link_text: str,
    *,
    reader: Callable[[str], tt.Timetable] | None = None,
) -> tuple[CalendarLink, tt.Timetable]:
    """링크로 시간표를 읽어 수업을 바꾸고 연결 행을 만들거나 고친다.

    reader는 링크 → Timetable. 기본은 everytime.read(공유 링크 자동).
    everytime.LinkInvalid · Unavailable은 그대로 올린다. 그때 이미 연결돼 있었으면
    status를 failed로 바꿔 둔다 — 커밋은 부르는 쪽.
    """
    share = everytime.share_id(link_text)  # 모양이 틀리면 아무것도 안 건드린다
    read = reader or everytime.read

    link = get_link(db, user_id, lock=True)
    try:
        table = read(link_text)
    except everytime.EverytimeError:
        if link is not None:
            link.status = LinkStatus.FAILED
            db.add(link)
        raise

    tt.replace_classes(db, user_id, table)
    if link is None:
        link = CalendarLink(
            user_id=user_id,
            kind=CalendarKind.EVERYTIME,
            external_ref=share,
            status=LinkStatus.OK,
        )
    link.external_ref = share
    link.status = LinkStatus.OK
    # 기록용 시각이라 시연 시계가 아니라 실제 시각이다(created_at과 같다).
    link.last_synced_at = real_now()
    db.add(link)
    db.flush()
    return link, table


def disconnect(db: Session, user_id: int) -> None:
    """연결 행과 에브리타임 수업을 지운다. 없어도 조용히 끝난다."""
    link = get_link(db, user_id, lock=True)
    if link is not None:
        db.delete(link)
    tt.remove_classes(db, user_id)
