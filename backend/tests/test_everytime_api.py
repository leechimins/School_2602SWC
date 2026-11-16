"""에브리타임 연결·끊기. 공유 페이지 읽기(everytime.fetch_xml)를 가짜로 바꿔 끼운다.

네트워크와 크롬을 타지 않는다. 가짜는 받은 공유 아이디를 남겨 두고,
정해 둔 XML을 돌려주거나 정해 둔 예외를 던진다.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, func, select

from app.integration import everytime
from app.integration import everytime_service as service
from app.integration.timetable import (
    ClassTime,
    Course,
    TermState,
    Timetable,
    term_label,
    term_range,
    term_state,
)
from app.me.models import ScheduleItem
from app.minutes.models import CalendarLink
from app.shared import demo_clock
from app.shared.base import KST
from app.shared.enums import LinkStatus, Recurrence, ScheduleKind, ScheduleSource
from app.shared.models import User

API = "/api/v1"
URL = f"{API}/me/integrations/everytime"
TODAY = datetime(2026, 11, 10, 9, 0, tzinfo=KST)
LINK = "https://everytime.kr/@AbCd1234"

# 11/6에 실제 공유 페이지에서 받은 모양(이름·과목만 바꿈).
XML = """<?xml version="1.0" encoding="UTF-8"?>
<response>
  <table year="2026" semester="2" status="1" identifier="AbCd1234">
    <subject id="1">
      <internal value="SD301"/>
      <name value="서비스디자인"/>
      <professor value="김교수"/>
      <time value="월,5/6 수,5/6">
        <data day="0" starttime="156" endtime="174" place="인A301"/>
        <data day="2" starttime="156" endtime="174" place="인A301"/>
      </time>
    </subject>
    <subject id="2">
      <name value="알고리즘"/>
      <professor value="한교수"/>
      <time value="화,6/7">
        <data day="1" starttime="198" endtime="213" place="인B303"/>
      </time>
    </subject>
    <subject id="3">
      <name value="온라인 교양"/>
      <time value=""/>
    </subject>
  </table>
</response>"""

XML_AGAIN = """<response><table year="2026" semester="2">
  <subject><name value="캡스톤"/><time><data day="4" starttime="120" endtime="156"/></time></subject>
</table></response>"""

XML_EMPTY = '<response><table year="2026" semester="2"></table></response>'
XML_PRIVATE = "<response></response>"


class FakeEverytime:
    def __init__(self) -> None:
        self.xml = XML
        self.error: Exception | None = None
        self.calls: list[str] = []

    def fetch_xml(self, share: str) -> str:
        self.calls.append(share)
        if self.error:
            raise self.error
        return self.xml


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeEverytime:
    fake = FakeEverytime()
    monkeypatch.setattr(everytime, "fetch_xml", fake.fetch_xml)
    monkeypatch.setattr(everytime, "configured", lambda: True)
    return fake


@pytest.fixture
def jisu(seeded: Session, login) -> User:
    demo_clock.set_clock(seeded, TODAY)
    seeded.commit()
    login("지수")
    return seeded.exec(select(User).where(User.name == "지수")).one()


def _rows(session: Session, user_id: int, source: ScheduleSource | None = None) -> list[ScheduleItem]:
    session.expire_all()
    query = select(ScheduleItem).where(ScheduleItem.user_id == user_id)
    if source is not None:
        query = query.where(ScheduleItem.source == source)
    return list(session.exec(query.order_by(ScheduleItem.group_id, ScheduleItem.weekday)))


def _others(session: Session, user_id: int) -> list[tuple]:
    """에브리타임이 아닌 내 행 + 남의 행 전부. 연결·끊기가 건드리면 안 되는 것."""
    session.expire_all()
    rows = session.exec(
        select(ScheduleItem).where(
            (ScheduleItem.user_id != user_id) | (ScheduleItem.source != ScheduleSource.EVERYTIME)
        )
    ).all()
    return sorted((r.id, r.user_id, r.source, r.weekday, r.start_min) for r in rows)


def _link(session: Session, user_id: int) -> CalendarLink | None:
    session.expire_all()
    return service.get_link(session, user_id)


def _add_manual(session: Session, user_id: int) -> None:
    session.add(
        ScheduleItem(
            user_id=user_id,
            group_id=900,
            source=ScheduleSource.MANUAL,
            kind=ScheduleKind.PARTTIME,
            title="카페 알바",
            recurrence=Recurrence.WEEKLY,
            weekday=5,
            start_min=600,
            end_min=900,
        )
    )
    session.commit()


def _connect(client: TestClient, url: str = LINK):
    return client.post(URL, json={"url": url})


# ── 연결 ─────────────────────────────────────────────────────────────


def test_연결하면_수업이_요일마다_한_줄로_들어간다(client, fake, jisu, seeded):
    res = _connect(client)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "everytime"
    assert body["connected"] is True
    assert body["status"] == "ok"
    assert body["account"] == "everytime.kr/@AbCd1234"
    assert body["imported_count"] == 2  # 시간 없는 온라인 강의는 빠진다
    assert body["term"] == "2026년 2학기"
    assert body["term_state"] == "current"
    assert body["last_synced_at"] is not None
    assert fake.calls == ["AbCd1234"]

    rows = _rows(seeded, jisu.id, ScheduleSource.EVERYTIME)
    assert [(r.title, r.weekday, r.start_min, r.end_min) for r in rows] == [
        ("서비스디자인", 0, 780, 870),  # 156 × 5 = 13:00, 174 × 5 = 14:30
        ("서비스디자인", 2, 780, 870),
        ("알고리즘", 1, 990, 1065),
    ]
    for r in rows:
        assert r.kind == ScheduleKind.CLASS
        assert r.recurrence == Recurrence.WEEKLY
        assert (r.valid_from, r.valid_to) == (date(2026, 9, 1), date(2026, 12, 31))


def test_과목마다_묶음이_하나고_기존_묶음_번호와_안_섞인다(client, fake, jisu, seeded):
    # 시드에 에브리타임 수업이 이미 있다. 그건 지워지므로 남는 묶음과만 안 섞이면 된다.
    _add_manual(seeded, jisu.id)
    seeded.expire_all()
    before_max = seeded.exec(
        select(func.max(ScheduleItem.group_id)).where(
            ScheduleItem.user_id == jisu.id,
            ScheduleItem.source != ScheduleSource.EVERYTIME,
        )
    ).one()
    _connect(client)
    rows = _rows(seeded, jisu.id, ScheduleSource.EVERYTIME)
    groups = {r.title: r.group_id for r in rows}
    assert rows[0].group_id == rows[1].group_id  # 서비스디자인 월·수
    assert groups["서비스디자인"] != groups["알고리즘"]
    assert min(groups.values()) > before_max


def test_다시_연결하면_이전_수업을_지우고_새로_넣는다(client, fake, jisu, seeded):
    _connect(client)
    fake.xml = XML_AGAIN
    res = _connect(client)
    assert res.status_code == 200
    assert res.json()["imported_count"] == 1
    rows = _rows(seeded, jisu.id, ScheduleSource.EVERYTIME)
    assert [(r.title, r.weekday) for r in rows] == [("캡스톤", 4)]
    seeded.expire_all()
    links = seeded.exec(select(CalendarLink).where(CalendarLink.user_id == jisu.id)).all()
    assert len(links) == 1


def test_같은_링크를_두_번_넣어도_중복이_없다(client, fake, jisu, seeded):
    _connect(client)
    _connect(client)
    assert len(_rows(seeded, jisu.id, ScheduleSource.EVERYTIME)) == 3


def test_직접_입력과_남의_시간표는_안_건드린다(client, fake, jisu, seeded):
    _add_manual(seeded, jisu.id)
    before = _others(seeded, jisu.id)
    assert any(source == ScheduleSource.MANUAL for _, uid, source, *_ in before if uid == jisu.id)
    _connect(client)
    fake.xml = XML_AGAIN
    _connect(client)
    assert _others(seeded, jisu.id) == before


def test_빈_시간표면_수업_0개로_연결된다(client, fake, jisu, seeded):
    fake.xml = XML_EMPTY
    res = _connect(client)
    assert res.status_code == 200
    assert res.json()["imported_count"] == 0
    assert _link(seeded, jisu.id).status == LinkStatus.OK


@pytest.mark.parametrize(
    "url",
    [
        "everytime.kr/@AbCd1234",
        "http://everytime.kr/@AbCd1234/",
        "https://www.everytime.kr/@AbCd1234?ref=share",
        "  https://everytime.kr/@AbCd1234  ",
        "https://everytime.kr/app/@AbCd1234",  # 휴대폰 앱에서 공유한 링크
    ],
)
def test_링크는_여러_모양을_받는다(client, fake, jisu, url):
    assert _connect(client, url).status_code == 200
    assert fake.calls == ["AbCd1234"]


# ── 실패 ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    ["https://everytime.kr/timetable/2026/2", "naver.com/@AbCd1234", "AbCd1234", "everytime.kr/@"],
)
def test_링크_모양이_아니면_400이고_읽지도_않는다(client, fake, jisu, seeded, url):
    res = _connect(client, url)
    assert res.status_code == 400
    assert res.json() == {
        "code": "EVERYTIME_LINK_INVALID",
        "message": "에타 시간표에서 복사한 공유 링크를 붙여 넣어 주세요.",
    }
    assert fake.calls == []
    assert _link(seeded, jisu.id) is None


def test_비공개_시간표면_400이고_연결이_안_생긴다(client, fake, jisu, seeded):
    before = [r.id for r in _rows(seeded, jisu.id, ScheduleSource.EVERYTIME)]
    fake.xml = XML_PRIVATE
    res = _connect(client)
    assert res.status_code == 400
    assert res.json() == {
        "code": "EVERYTIME_LINK_INVALID",
        "message": "시간표를 찾지 못했어요. 에브리타임에서 시간표가 전체 공개인지 확인해 주세요.",
    }
    assert _link(seeded, jisu.id) is None
    # 시드에 있던 수업은 그대로다
    assert [r.id for r in _rows(seeded, jisu.id, ScheduleSource.EVERYTIME)] == before


def test_깨진_응답이면_400(client, fake, jisu):
    fake.xml = "<html>차단</html"
    assert _connect(client).json()["code"] == "EVERYTIME_LINK_INVALID"


def test_에브리타임이_막히면_503(client, fake, jisu, seeded):
    fake.error = everytime.Unavailable("page 403")
    res = _connect(client)
    assert res.status_code == 503
    assert res.json() == {
        "code": "EVERYTIME_UNAVAILABLE",
        "message": "에브리타임을 잠시 못 읽었어요. 잠시 후 다시 해 주세요.",
    }
    assert _link(seeded, jisu.id) is None


@pytest.mark.parametrize(
    ("error", "code", "xml"),
    [
        (everytime.Unavailable("timeout"), "EVERYTIME_UNAVAILABLE", XML),
        (None, "EVERYTIME_LINK_INVALID", XML_PRIVATE),
    ],
)
def test_다시_불러오기가_실패하면_이전_수업은_남고_failed(client, fake, jisu, seeded, error, code, xml):
    _connect(client)
    before = [(r.title, r.weekday) for r in _rows(seeded, jisu.id, ScheduleSource.EVERYTIME)]
    fake.error, fake.xml = error, xml
    res = _connect(client)
    assert res.json()["code"] == code
    assert [(r.title, r.weekday) for r in _rows(seeded, jisu.id, ScheduleSource.EVERYTIME)] == before
    assert _link(seeded, jisu.id).status == LinkStatus.FAILED

    # 다시 되면 ok로 돌아온다
    fake.error, fake.xml = None, XML
    assert _connect(client).json()["status"] == "ok"


def test_연동이_서버에_없으면_503_NOT_CONFIGURED이고_직접_입력하라고_한다(client, fake, jisu, monkeypatch):
    # 다시 해도 안 되는 경우라 "잠시 후 다시"(EVERYTIME_UNAVAILABLE)와 코드를 나눈다.
    monkeypatch.setattr(everytime, "configured", lambda: False)
    res = _connect(client)
    assert res.status_code == 503
    assert res.json()["code"] == "EVERYTIME_NOT_CONFIGURED"
    assert "직접" in res.json()["message"]
    assert fake.calls == []


def test_configured는_curl_cffi_설치_여부를_본다(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(everytime, "find_spec", lambda name: seen.append(name) or object())
    assert everytime.configured() is True
    assert seen == ["curl_cffi"]
    monkeypatch.setattr(everytime, "find_spec", lambda name: None)
    assert everytime.configured() is False


# ── 시간표 요청 (curl_cffi를 가짜로) ───────────────────────────────────


class FakeHttp:
    """curl_cffi.requests.post 자리. 받은 인자를 남기고 정해 둔 응답이나 예외를 낸다."""

    def __init__(self) -> None:
        self.status = 200
        self.text = XML
        self.error: Exception | None = None
        self.calls: list[tuple[str, dict]] = []

    def post(self, url: str, **kw):
        self.calls.append((url, kw))
        if self.error:
            raise self.error
        return type("Res", (), {"status_code": self.status, "text": self.text})()


@pytest.fixture
def http(monkeypatch: pytest.MonkeyPatch) -> FakeHttp:
    from curl_cffi import requests as cffi

    fake = FakeHttp()
    monkeypatch.setattr(cffi, "post", fake.post)
    monkeypatch.setattr(everytime, "configured", lambda: True)
    return fake


def test_시간표_요청은_크롬_흉내로_공유_아이디를_POST(http):
    assert everytime.fetch_xml("AbCd1234") == XML
    [(url, kw)] = http.calls
    assert url == "https://api.everytime.kr/find/timetable/table/friend"
    assert kw["data"] == {"identifier": "AbCd1234", "friendInfo": "true"}
    assert kw["impersonate"] == "chrome"  # 빼면 403(TLS 지문)
    assert kw["timeout"] == everytime.TIMEOUT_S


@pytest.mark.parametrize("status", [403, 500])
def test_시간표_요청이_200이_아니면_Unavailable(http, status):
    http.status, http.text = status, "The server detected abnormal access"
    with pytest.raises(everytime.Unavailable):
        everytime.fetch_xml("AbCd1234")


def test_시간표_요청이_시간을_넘기면_Unavailable(http):
    from curl_cffi.requests.exceptions import Timeout

    http.error = Timeout("timed out")
    with pytest.raises(everytime.Unavailable):
        everytime.fetch_xml("AbCd1234")


def test_API_에브리타임이_403이면_503_다시_하기(client, http, jisu, seeded):
    http.status = 403
    res = _connect(client)
    assert res.status_code == 503
    assert res.json()["code"] == "EVERYTIME_UNAVAILABLE"
    assert _link(seeded, jisu.id) is None


def test_API_없는_아이디_비공개는_400_시간표_없음(client, http, jisu):
    # 11/15 실측: 없는 아이디도 200 + <response>-1</response>
    http.text = '<?xml version="1.0" encoding="UTF-8"?>\n<response>-1</response>'
    res = _connect(client)
    assert res.status_code == 400
    assert res.json()["code"] == "EVERYTIME_LINK_INVALID"
    assert "전체 공개" in res.json()["message"]


def test_API_실제_요청_경로로_수업이_들어온다(client, http, jisu, seeded):
    res = _connect(client)
    assert res.status_code == 200
    assert http.calls[0][1]["data"]["identifier"] == "AbCd1234"
    assert len(_rows(seeded, jisu.id, ScheduleSource.EVERYTIME)) == 3


def test_로그인_안_하면_401(client, fake, seeded):
    assert _connect(client).status_code == 401


# ── 끊기 ─────────────────────────────────────────────────────────────


def test_끊으면_연결과_에브리타임_수업만_지운다(client, fake, jisu, seeded):
    _add_manual(seeded, jisu.id)
    _connect(client)
    before = _others(seeded, jisu.id)
    res = client.delete(URL)
    assert res.status_code == 204
    assert _link(seeded, jisu.id) is None
    assert _rows(seeded, jisu.id, ScheduleSource.EVERYTIME) == []
    assert _others(seeded, jisu.id) == before


def test_연결이_없어도_끊기는_204(client, fake, jisu):
    assert client.delete(URL).status_code == 204


# ── 읽기·넣기 규칙 (단위) ─────────────────────────────────────────────


def test_파서는_시각_밖의_것을_버린다():
    table = everytime.parse(XML)
    assert (table.year, table.semester) == (2026, "2")
    assert table.courses[0] == Course(
        "서비스디자인", (ClassTime(0, 780, 870), ClassTime(2, 780, 870))
    )
    assert table.courses[2].times == ()


def test_학기_범위와_이름():
    assert term_range(Timetable(2026, "1", ())) == (date(2026, 3, 1), date(2026, 6, 30))
    assert term_range(Timetable(2026, "2", ())) == (date(2026, 9, 1), date(2026, 12, 31))
    # 계절학기처럼 모르는 학기 값은 그 해 전체. 연도도 모르면 범위 없음
    assert term_range(Timetable(2026, "S", ())) == (date(2026, 1, 1), date(2026, 12, 31))
    assert term_range(Timetable(2026, None, ())) == (date(2026, 1, 1), date(2026, 12, 31))
    assert term_range(Timetable(None, "2", ())) == (None, None)
    assert term_label(Timetable(2026, "S", ())) == "2026년 S"
    assert term_label(Timetable(None, None, ())) is None


@pytest.mark.parametrize(
    ("year", "semester", "today", "state"),
    [
        (2026, "2", date(2026, 11, 10), TermState.CURRENT),
        (2026, "2", date(2026, 9, 1), TermState.CURRENT),  # 첫날
        (2026, "2", date(2026, 12, 31), TermState.CURRENT),  # 마지막 날
        (2026, "1", date(2026, 11, 10), TermState.PAST),
        (2024, "2", date(2026, 11, 10), TermState.PAST),
        (2026, "2", date(2026, 8, 20), TermState.UPCOMING),  # 방학 중에 다음 학기를 미리
        (2027, "1", date(2026, 12, 20), TermState.UPCOMING),
        (2025, "S", date(2026, 7, 10), TermState.PAST),  # 지난 해 계절학기
        (2026, "S", date(2026, 7, 10), TermState.CURRENT),  # 올해 계절학기, 지금이 계절학기
        (None, None, date(2026, 11, 10), None),
    ],
)
def test_학기_상태는_오늘이_학기_범위의_어디인지(year, semester, today, state):
    assert term_state(Timetable(year, semester, ()), today) == state


def test_제약에_걸릴_시각은_버리고_나머지는_넣는다(client, fake, jisu, seeded):
    fake.xml = """<response><table year="2026" semester="2"><subject><name value="실험"/><time>
      <data day="0" starttime="120" endtime="120"/>
      <data day="9" starttime="120" endtime="130"/>
      <data day="3" starttime="120" endtime="300"/>
      <data day="3" starttime="120" endtime="130"/>
      <data day="3" starttime="120" endtime="130"/>
    </time></subject></table></response>"""
    assert _connect(client).status_code == 200
    rows = _rows(seeded, jisu.id, ScheduleSource.EVERYTIME)
    assert [(r.weekday, r.start_min, r.end_min) for r in rows] == [(3, 600, 650)]


def test_지난_학기_링크면_이번_학기_조율을_막지_않는다(client, fake, jisu, seeded):
    from datetime import timedelta

    from app.meeting.slots import expand_busy

    fake.xml = XML.replace('year="2026" semester="2"', 'year="2024" semester="2"')
    body = _connect(client).json()
    assert body["term"] == "2024년 2학기"
    assert body["term_state"] == "past"  # 저장은 하고 화면이 이번 학기 링크를 안내
    assert body["imported_count"] == 2
    rows = _rows(seeded, jisu.id, ScheduleSource.EVERYTIME)
    start = TODAY.replace(hour=0)
    assert expand_busy(rows, start, start + timedelta(days=7)) == []


def test_지난_해_계절학기_링크도_이번_주_조율을_막지_않는다(client, fake, jisu, seeded):
    from datetime import timedelta

    from app.meeting.slots import expand_busy

    fake.xml = XML.replace('year="2026" semester="2"', 'year="2025" semester="S"')
    body = _connect(client).json()
    assert body["term_state"] == "past"
    rows = _rows(seeded, jisu.id, ScheduleSource.EVERYTIME)
    start = TODAY.replace(hour=0)
    assert expand_busy(rows, start, start + timedelta(days=7)) == []


def test_학기를_모르면_term_state는_null(client, fake, jisu):
    fake.xml = XML.replace(' year="2026" semester="2"', "")
    body = _connect(client).json()
    assert body["term"] is None
    assert body["term_state"] is None


def test_비공개_시간표_링크는_수업_0개가_아니라_400_시간표_없음(client, fake, jisu, seeded):
    # 11/16 실측: 비공개면 200 + <table status="-2"/>(빈 표)와 사용자 이름이 온다
    fake.xml = (
        '<?xml version="1.0" encoding="UTF-8"?><response>'
        '<table year="2023" semester="1" status="-2" identifier="AbCd1234"/>'
        '<user name="누구"/></response>'
    )
    before = [r.id for r in _rows(seeded, jisu.id, ScheduleSource.EVERYTIME)]
    res = _connect(client)
    assert res.status_code == 400
    assert res.json()["code"] == "EVERYTIME_LINK_INVALID"
    assert "전체 공개" in res.json()["message"]
    assert [r.id for r in _rows(seeded, jisu.id, ScheduleSource.EVERYTIME)] == before
