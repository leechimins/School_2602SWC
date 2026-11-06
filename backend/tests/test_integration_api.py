"""구글 캘린더 연결·동기화·끊기. 구글 호출(google_calendar)을 가짜로 바꿔 끼운다.

네트워크를 타지 않는다. 가짜는 받은 시간 범위와 토큰을 남겨 두어
"시연 시계 기준으로 읽었나", "갱신한 토큰으로 다시 읽었나"를 본다.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.integration import google_calendar as google
from app.integration import service as integration
from app.me.models import ScheduleItem
from app.minutes.models import CalendarLink
from app.shared import demo_clock
from app.shared.base import KST
from app.shared.enums import (
    Recurrence,
    ScheduleKind,
    ScheduleSource,
)
from app.shared.models import User

API = "/api/v1"
URL = f"{API}/me/integrations/google-calendar"
TODAY = datetime(2026, 11, 10, 9, 0, tzinfo=KST)

ACCESS = "ya29.접근-토큰-비밀"
REFRESH = "1//갱신-토큰-비밀"
ACCOUNT = "jisu@example.com"


def _timed(day: int, start: str, end: str, **extra) -> dict:
    return {
        "summary": "치과 예약",
        "location": "강남역",
        "start": {"dateTime": f"2026-11-{day:02d}T{start}:00+09:00"},
        "end": {"dateTime": f"2026-11-{day:02d}T{end}:00+09:00"},
        **extra,
    }


def _all_day(start: str, end: str, **extra) -> dict:
    return {"summary": "일본 여행", "start": {"date": start}, "end": {"date": end}, **extra}


EVENTS = [
    _timed(12, "14:00", "15:00"),
    # 구글은 종일 일정을 기본으로 "한가함"으로 둔다. 그래도 넣는다.
    _all_day("2026-11-07", "2026-11-11", transparency="transparent"),
    # 아래 셋은 빠져야 한다.
    _timed(13, "10:00", "11:00", transparency="transparent"),
    _timed(14, "10:00", "11:00", status="cancelled"),
    _timed(
        15,
        "10:00",
        "11:00",
        attendees=[{"email": ACCOUNT, "self": True, "responseStatus": "declined"}],
    ),
]


class FakeGoogle:
    def __init__(self) -> None:
        self.events: list[dict] = list(EVENTS)
        self.refresh_token: str | None = REFRESH
        self.ranges: list[tuple[datetime, datetime]] = []
        self.list_tokens: list[str] = []

    def exchange_code(self, code: str) -> google.Tokens:
        return google.Tokens(ACCESS, self.refresh_token)

    def primary_account(self, access_token: str) -> str:
        return ACCOUNT

    def list_events(self, access_token: str, time_min: datetime, time_max: datetime) -> list[dict]:
        self.list_tokens.append(access_token)
        self.ranges.append((time_min, time_max))
        return self.events


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeGoogle:
    fake = FakeGoogle()
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
    for name in ("exchange_code", "primary_account", "list_events"):
        monkeypatch.setattr(google, name, getattr(fake, name))
    return fake


@pytest.fixture
def jisu(seeded: Session, login) -> User:
    demo_clock.set_clock(seeded, TODAY)
    seeded.commit()
    login("지수")
    return seeded.exec(select(User).where(User.name == "지수")).one()


def _items(session: Session, user_id: int, source: ScheduleSource) -> list[ScheduleItem]:
    session.expire_all()
    return list(
        session.exec(
            select(ScheduleItem)
            .where(ScheduleItem.user_id == user_id, ScheduleItem.source == source)
            .order_by(ScheduleItem.start_at)
        )
    )


def _link(session: Session, user_id: int) -> CalendarLink | None:
    session.expire_all()
    return integration.get_link(session, user_id)


def _connect(client: TestClient):
    return client.post(URL, json={"code": "4/인증코드"})


# ── 연결 ─────────────────────────────────────────────────────────────


def test_연결하면_약속이_제목없이_바쁨으로_들어간다(client, fake, jisu, seeded):
    res = _connect(client)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["connected"] is True
    assert body["status"] == "ok"
    assert body["account"] == ACCOUNT
    assert body["imported_count"] == 2
    assert body["last_synced_at"] is not None

    items = _items(seeded, jisu.id, ScheduleSource.GOOGLE)
    assert [(i.start_at, i.end_at) for i in items] == [
        # 여러 날 종일 일정은 한 구간. 끝 날짜(11/11)는 포함하지 않는다.
        (datetime(2026, 11, 7, tzinfo=KST), datetime(2026, 11, 11, tzinfo=KST)),
        (datetime(2026, 11, 12, 14, tzinfo=KST), datetime(2026, 11, 12, 15, tzinfo=KST)),
    ]
    for item in items:
        assert item.title is None
        assert item.kind == ScheduleKind.APPOINTMENT
        assert item.recurrence == Recurrence.ONCE
        assert item.start_at.utcoffset() == timedelta(hours=9)


def test_응답에_토큰이_없다(client, fake, jisu):
    res = _connect(client)
    assert ACCESS not in res.text
    assert REFRESH not in res.text
    assert "token" not in res.json()


def test_토큰은_로그에_남지_않는다(client, fake, jisu, caplog):
    with caplog.at_level(logging.DEBUG):
        _connect(client)
        client.post(f"{URL}/sync")
    assert ACCESS not in caplog.text
    assert REFRESH not in caplog.text


def test_토큰은_저장된다(client, fake, jisu, seeded):
    _connect(client)
    link = _link(seeded, jisu.id)
    assert link.access_token == ACCESS
    assert link.refresh_token == REFRESH
    assert link.external_ref == ACCOUNT


def test_시연_시계_오늘부터_5주를_읽는다(client, fake, jisu):
    _connect(client)
    start, end = fake.ranges[-1]
    assert start == datetime(2026, 11, 10, tzinfo=KST)
    assert end == datetime(2026, 12, 15, tzinfo=KST)


def test_로그인_안_하면_401(client, fake, seeded):
    assert client.post(URL, json={"code": "x"}).status_code == 401
    assert client.post(f"{URL}/sync").status_code == 401
    assert client.delete(URL).status_code == 401


def test_다시_연결할_때_갱신_토큰을_안_주면_있던_것을_지킨다(client, fake, jisu, seeded):
    _connect(client)
    fake.refresh_token = None
    assert _connect(client).status_code == 200
    assert _link(seeded, jisu.id).refresh_token == REFRESH
    assert len(seeded.exec(select(CalendarLink)).all()) == 1


# ── 동기화 ───────────────────────────────────────────────────────────


def _manual(session: Session, user_id: int) -> None:
    session.add(
        ScheduleItem(
            user_id=user_id,
            source=ScheduleSource.MANUAL,
            kind=ScheduleKind.PARTTIME,
            recurrence=Recurrence.WEEKLY,
            weekday=0,
            start_min=18 * 60,
            end_min=22 * 60,
            valid_from=date(2026, 9, 1),
            valid_to=date(2026, 12, 20),
        )
    )
    session.commit()


def test_동기화는_구글_약속만_통째로_바꾼다(client, fake, jisu, seeded):
    _connect(client)
    _manual(seeded, jisu.id)
    manual_before = len(_items(seeded, jisu.id, ScheduleSource.MANUAL))

    fake.events = [_timed(20, "09:00", "10:00")]
    res = client.post(f"{URL}/sync")
    assert res.status_code == 200, res.text
    assert res.json()["imported_count"] == 1

    google_items = _items(seeded, jisu.id, ScheduleSource.GOOGLE)
    assert [i.start_at for i in google_items] == [datetime(2026, 11, 20, 9, tzinfo=KST)]
    assert len(_items(seeded, jisu.id, ScheduleSource.MANUAL)) == manual_before


def test_동기화는_다른_사람_약속을_안_건드린다(client, fake, jisu, seeded, login):
    _connect(client)
    login("민지")
    _connect(client)
    minji = seeded.exec(select(User).where(User.name == "민지")).one()

    fake.events = []
    client.post(f"{URL}/sync")
    assert _items(seeded, minji.id, ScheduleSource.GOOGLE) == []
    assert len(_items(seeded, jisu.id, ScheduleSource.GOOGLE)) == 2


def test_연결_안_했으면_동기화는_404(client, fake, jisu):
    res = client.post(f"{URL}/sync")
    assert res.status_code == 404
    assert res.json()["code"] == "NOT_CONNECTED"


# ── 끊기 ─────────────────────────────────────────────────────────────


def test_끊으면_연결과_구글_약속이_지워지고_직접_입력은_남는다(client, fake, jisu, seeded):
    _connect(client)
    _manual(seeded, jisu.id)
    manual_before = len(_items(seeded, jisu.id, ScheduleSource.MANUAL))

    assert client.delete(URL).status_code == 204
    assert _link(seeded, jisu.id) is None
    assert _items(seeded, jisu.id, ScheduleSource.GOOGLE) == []
    assert len(_items(seeded, jisu.id, ScheduleSource.MANUAL)) == manual_before


def test_연결이_없어도_끊기는_204(client, fake, jisu):
    assert client.delete(URL).status_code == 204


# ── 바쁨 변환 ────────────────────────────────────────────────────────


def test_다른_시간대_약속은_한국_시간으로_바꾼다():
    event = {
        "start": {"dateTime": "2026-11-12T05:00:00Z"},
        "end": {"dateTime": "2026-11-12T06:00:00Z"},
    }
    [busy] = integration.to_busy([event])
    assert busy.start_at == datetime(2026, 11, 12, 14, tzinfo=KST)
    assert busy.start_at.utcoffset() == timedelta(hours=9)


def test_0분짜리_약속은_뺀다():
    assert integration.to_busy([_timed(12, "14:00", "14:00")]) == []
