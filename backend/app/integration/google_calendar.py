"""구글 호출이 일어나는 유일한 곳. 레인 B.

토큰 교환·갱신·계정 확인·약속 읽기만 한다. 무엇을 "바쁨"으로 넣을지는
service.py가 정한다 — 테스트가 이 파일의 함수만 가짜로 바꿔 끼우면
네트워크 없이 연결·동기화 전체를 돌릴 수 있게 하려는 것이다.

**토큰을 로그·예외 문장에 넣지 않는다.** 실패는 종류만 담은 예외로 올리고,
구글이 돌려준 본문(토큰이 섞일 수 있다)은 버린다.

구글 라이브러리를 쓰지 않는다. 엔드포인트 네 개라 이미 있는 httpx로 충분하고,
google-auth·google-api-python-client를 들이면 의존성만 무거워진다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

import httpx
from dotenv import load_dotenv

load_dotenv()

TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_URL = "https://www.googleapis.com/calendar/v3/calendars/primary"
SCOPE = "https://www.googleapis.com/auth/calendar.readonly"

# 프론트가 구글 팝업(GIS initCodeClient, ux_mode=popup)으로 코드를 받으면
# redirect_uri는 주소가 아니라 이 글자다. 그래서 콜백 경로를 따로 두지 않는다.
POPUP_REDIRECT_URI = "postmessage"

TIMEOUT_SEC = 10.0
# 한 페이지 250개 × 4. 5주 동안 약속이 천 개를 넘는 사람은 없다고 본다.
MAX_PAGES = 4


class GoogleError(Exception):
    """구글 호출 실패. 문장에 토큰·응답 본문을 담지 않는다."""


class InvalidGrant(GoogleError):
    """코드나 갱신 토큰이 더는 안 통한다. 다시 연결해야 한다."""


class Unauthorized(GoogleError):
    """접근 토큰이 만료됐다. 갱신 토큰으로 새로 받으면 된다."""


class Unavailable(GoogleError):
    """구글이 안 받거나 시간이 넘었다. 잠시 후 다시 하면 된다."""


@dataclass(frozen=True)
class Tokens:
    access_token: str
    # 사용자가 전에 허락한 적이 있으면 구글이 안 줄 수 있다.
    refresh_token: str | None


def _client() -> tuple[str, str] | None:
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    if not client_id or not secret:
        return None
    return client_id, secret


def configured() -> bool:
    """클라이언트 ID·시크릿이 다 있나. 없으면 연동만 빠지고 앱은 돈다."""
    return _client() is not None


def _token_request(data: dict[str, str]) -> dict:
    client = _client()
    if client is None:
        raise Unavailable("구글 클라이언트 설정이 없다")
    client_id, secret = client
    try:
        res = httpx.post(
            TOKEN_URL,
            data={**data, "client_id": client_id, "client_secret": secret},
            timeout=TIMEOUT_SEC,
        )
    except httpx.HTTPError as exc:
        raise Unavailable(type(exc).__name__) from None
    if res.status_code == 200:
        return res.json()
    # 400 invalid_grant: 코드를 이미 썼거나, 갱신 토큰이 취소·만료됐다.
    try:
        error = res.json().get("error")
    except ValueError:
        error = None
    if res.status_code in (400, 401) and error in ("invalid_grant", "invalid_request"):
        raise InvalidGrant(error)
    raise Unavailable(f"token {res.status_code}")


def exchange_code(code: str) -> Tokens:
    """팝업에서 받은 인증 코드를 토큰으로 바꾼다."""
    body = _token_request(
        {
            "code": code,
            "redirect_uri": POPUP_REDIRECT_URI,
            "grant_type": "authorization_code",
        }
    )
    return Tokens(body["access_token"], body.get("refresh_token"))


def refresh(refresh_token: str) -> str:
    """갱신 토큰으로 새 접근 토큰을 받는다."""
    body = _token_request(
        {"refresh_token": refresh_token, "grant_type": "refresh_token"}
    )
    return body["access_token"]


def _get(access_token: str, url: str, params: dict | None = None) -> dict:
    try:
        res = httpx.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=TIMEOUT_SEC,
        )
    except httpx.HTTPError as exc:
        raise Unavailable(type(exc).__name__) from None
    if res.status_code == 200:
        return res.json()
    if res.status_code == 401:
        raise Unauthorized("access token")
    # 403은 Calendar API가 꺼졌거나 권한을 덜 받은 경우다. 사용자가 할 수 있는
    # 일이 다시 연결뿐이라 InvalidGrant와 같게 본다.
    if res.status_code == 403:
        raise InvalidGrant("forbidden")
    raise Unavailable(f"calendar {res.status_code}")


def primary_account(access_token: str) -> str:
    """기본 캘린더의 id. 구글 계정 이메일이다(calendar_link.external_ref)."""
    return _get(access_token, CALENDAR_URL)["id"]


def list_events(access_token: str, time_min: datetime, time_max: datetime) -> list[dict]:
    """기본 캘린더의 약속을 구글이 준 모양 그대로 돌려준다.

    singleEvents=true라 반복 약속은 구글이 하나씩 펼쳐 준다. 여러 날에 걸친
    종일 일정은 펼치지 않고 하나로 온다(end.date는 그날을 포함하지 않는다).
    """
    events: list[dict] = []
    page_token: str | None = None
    for _ in range(MAX_PAGES):
        params = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "timeZone": "Asia/Seoul",
            "maxResults": 250,
        }
        if page_token:
            params["pageToken"] = page_token
        body = _get(access_token, f"{CALENDAR_URL}/events", params)
        events.extend(body.get("items", []))
        page_token = body.get("nextPageToken")
        if not page_token:
            break
    return events
