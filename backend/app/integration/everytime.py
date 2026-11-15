"""에브리타임 공유 링크를 읽는 유일한 곳. 레인 B.

링크 → 공유 아이디 → 시간표 XML → `Timetable`. 무엇을 어떻게 넣을지는
timetable.py가 정한다. 테스트는 `fetch_xml`만 가짜로 바꿔 끼운다.

**읽는 방법.** 공유 페이지가 스스로 부르는 `find/timetable/table/friend`에 POST를
한 번 보낸다. 일반 HTTP 클라이언트로 보내면 403인데(11/5·11/6) 원인은 TLS 지문이라,
`curl_cffi`로 크롬의 TLS 지문을 흉내 내면 열린다(11/15 확인, 로컬·Colab 모두 200).
페이지를 먼저 열거나 쿠키를 받을 필요는 없다. 예전에는 헤드리스 크롬으로 페이지를
열어 응답을 가로챘다(#65에서 교체).
사용자가 "불러오기"를 누를 때만 한 번 부른다 — 주기 동기화는 하지 않는다(차단 위험).

**캡처(이미지 → AI)를 붙일 때**는 이미지에서 `Timetable`을 만드는 파일을 따로 두고,
everytime_service.connect에 reader로 넘기면 된다(#66).

`curl_cffi`가 없으면 `configured()`가 False이고 연동만 빠진다.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from importlib.util import find_spec

from app.integration.timetable import ClassTime, Course, Timetable

XML_URL = "https://api.everytime.kr/find/timetable/table/friend"
# 공유 페이지에서 부르는 것처럼 보이게 한다.
_HEADERS = {
    "Origin": "https://everytime.kr",
    "Referer": "https://everytime.kr/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}
# 11/15 실측: 로컬 2초, Colab(해외 데이터센터) 4초.
TIMEOUT_S = 15

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
    """링크 모양이 아니다. 에브리타임 페이지를 열기 전에 걸러진다."""


class TimetableNotFound(LinkInvalid):
    """링크 모양은 맞는데 열어 보니 시간표가 없다(비공개·삭제·없는 아이디).

    에브리타임 응답만으로는 비공개와 없는 아이디를 가를 수 없어 하나로 둔다.
    """


class Unavailable(EverytimeError):
    """막혔거나 시간이 넘었거나 네트워크가 끊겼다. 잠시 후 다시 하면 된다."""


def configured() -> bool:
    """`curl_cffi`가 깔려 있나. 없으면 다시 해도 안 되니 라우터가 다른 코드로 답한다."""
    return find_spec("curl_cffi") is not None


def share_id(link: str) -> str:
    """붙여 넣은 링크에서 공유 아이디를 뽑는다. 아니면 LinkInvalid."""
    match = _LINK.match(link.strip())
    if not match:
        raise LinkInvalid("link")
    return match.group(1)


def fetch_xml(share: str) -> str:
    """시간표 XML을 받아 온다. 없는 아이디·비공개도 200(`<response>-1</response>`)이라
    여기서는 가리지 않고 parse가 TimetableNotFound로 거른다."""
    try:
        from curl_cffi import CurlError
        from curl_cffi import requests as http
    except ImportError:
        raise Unavailable("curl_cffi") from None

    try:
        res = http.post(
            XML_URL,
            data={"identifier": share, "friendInfo": "true"},
            headers=_HEADERS,
            impersonate="chrome",
            timeout=TIMEOUT_S,
        )
    except CurlError as exc:
        # 시간 초과·연결 끊김·TLS 오류가 다 여기로 온다(requests 쪽 예외도 CurlError 하위).
        raise Unavailable(type(exc).__name__) from None
    if res.status_code != 200:
        raise Unavailable(f"xml {res.status_code}")
    return res.text


def _int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _value(subject: ET.Element, tag: str) -> str:
    node = subject.find(tag)
    return (node.get("value") or "") if node is not None else ""


def parse(xml: str) -> Timetable:
    """시간표 XML → Timetable. 시간표가 없으면 TimetableNotFound.

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
        raise TimetableNotFound("xml") from None
    table = root if root.tag == "table" else root.find(".//table")
    if table is None:
        # 비공개·없는 공유 아이디면 <response>만 온다.
        raise TimetableNotFound("no table")

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
    """붙여 넣은 링크 하나로 시간표까지. LinkInvalid(TimetableNotFound 포함) · Unavailable을 올린다."""
    return parse(fetch_xml(share_id(link)))
