"""에브리타임 공유 링크를 읽는 유일한 곳. 레인 B.

링크 → 공유 아이디 → 시간표 XML → `Timetable`. 무엇을 어떻게 넣을지는
timetable.py가 정한다. 테스트는 `fetch_xml`만 가짜로 바꿔 끼운다.

**읽는 방법.** 서버에서 바로 요청하면 403이다(11/5·11/6 확인). 헤드리스 크롬으로
공유 페이지를 열고, 페이지가 스스로 부르는 `find/timetable/table/friend`의 응답을
가로챈다. 자동화 표시(브라우저 이름의 Headless, webdriver 플래그)를 지워야 열린다.
사용자가 "불러오기"를 누를 때만 한 번 연다 — 주기 동기화는 하지 않는다(차단 위험).

**나중에 캡처(이미지 → AI)로 바꿀 때**는 이 파일 대신 이미지에서 `Timetable`을
만드는 파일을 두고, everytime_service.connect에서 부르는 함수만 바꾸면 된다.

Playwright가 없거나 크롬이 안 깔려 있으면 `configured()`가 False이고 연동만 빠진다.
설치: `pip install playwright && python -m playwright install chromium`
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from importlib.util import find_spec

from app.integration.timetable import ClassTime, Course, Timetable

SHARE_PAGE = "https://everytime.kr/@{share_id}"
XML_PATH = "/find/timetable/table/friend"
# 11/8 실측: 공유 페이지 응답 5초 + 시간표 응답 5초 = 약 11초. 에브리타임 쪽이 느리다.
TIMEOUT_MS = 25_000

# everytime.kr/@아이디. 앞의 https://·www.·m. 과 뒤의 / ?쿼리는 있어도 된다.
# 휴대폰 앱에서 공유하면 everytime.kr/app/@아이디 로 나온다.
_LINK = re.compile(
    r"^(?:https?://)?(?:www\.|m\.)?everytime\.kr/(?:app/)?@([A-Za-z0-9_-]{1,64})/?(?:[?#].*)?$"
)

# XML의 시각은 5분 단위다(198 → 990분 = 16:30).
_UNIT_MIN = 5


class EverytimeError(Exception):
    """에브리타임 읽기 실패. 문장에 응답 본문을 담지 않는다."""


class LinkInvalid(EverytimeError):
    """링크 모양이 아니거나, 열었는데 시간표가 없다(비공개·삭제)."""


class Unavailable(EverytimeError):
    """막혔거나 시간이 넘었거나 크롬이 없다. 잠시 후 다시 하면 된다."""


def configured() -> bool:
    return find_spec("playwright") is not None


def share_id(link: str) -> str:
    """붙여 넣은 링크에서 공유 아이디를 뽑는다. 아니면 LinkInvalid."""
    match = _LINK.match(link.strip())
    if not match:
        raise LinkInvalid("link")
    return match.group(1)


def fetch_xml(share: str) -> str:
    """공유 페이지를 열어 시간표 XML을 받아 온다."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise Unavailable("playwright") from None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            try:
                # 헤드리스 크롬은 이름에 HeadlessChrome을 단다. 일반 크롬 이름으로 바꾼다.
                agent = (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    f"(KHTML, like Gecko) Chrome/{browser.version} Safari/537.36"
                )
                context = browser.new_context(user_agent=agent, locale="ko-KR")
                context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                page = context.new_page()
                with page.expect_response(
                    lambda r: XML_PATH in r.url, timeout=TIMEOUT_MS
                ) as caught:
                    # load까지 기다리면 광고·분석 스크립트 때문에 시간을 넘길 때가 있다.
                    # 시간표 요청은 페이지 스크립트가 보내므로 DOM까지만 기다린다.
                    opened = page.goto(
                        SHARE_PAGE.format(share_id=share),
                        timeout=TIMEOUT_MS,
                        wait_until="domcontentloaded",
                    )
                    if opened is not None and opened.status == 404:
                        raise LinkInvalid("page 404")
                    if opened is not None and opened.status >= 400:
                        raise Unavailable(f"page {opened.status}")
                res = caught.value
                if res.status != 200:
                    raise Unavailable(f"xml {res.status}")
                return res.text()
            finally:
                browser.close()
    except EverytimeError:
        raise
    except PlaywrightError as exc:
        # 시간 초과·크롬 미설치·네트워크 끊김이 다 여기로 온다.
        raise Unavailable(type(exc).__name__) from None


def _int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _value(subject: ET.Element, tag: str) -> str:
    node = subject.find(tag)
    return (node.get("value") or "") if node is not None else ""


def parse(xml: str) -> Timetable:
    """시간표 XML → Timetable. 시간표가 없으면 LinkInvalid.

    <table year="2024" semester="2">
      <subject>
        <name value="알고리즘"/>
        <time value="화,6/7">
          <data day="1" starttime="198" endtime="213" place="인A301"/>

    교수·강의실·이름 등 수업 시각 밖의 것은 버린다.
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        raise LinkInvalid("xml") from None
    table = root if root.tag == "table" else root.find(".//table")
    if table is None:
        # 비공개·없는 공유 아이디면 <response>만 온다.
        raise LinkInvalid("no table")

    courses: list[Course] = []
    for subject in table.iter("subject"):
        times: list[ClassTime] = []
        for data in subject.iter("data"):
            day = _int(data.get("day"))
            start = _int(data.get("starttime"))
            end = _int(data.get("endtime"))
            if day is None or start is None or end is None:
                continue
            times.append(ClassTime(day, start * _UNIT_MIN, end * _UNIT_MIN))
        courses.append(Course(_value(subject, "name"), tuple(times)))

    return Timetable(
        year=_int(table.get("year")),
        semester=table.get("semester") or None,
        courses=tuple(courses),
    )


def read(link: str) -> Timetable:
    """붙여 넣은 링크 하나로 시간표까지. LinkInvalid · Unavailable을 올린다."""
    return parse(fetch_xml(share_id(link)))
