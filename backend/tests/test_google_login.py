"""구글 로그인 — POST /sessions/google. 구글 호출은 가짜로 바꿔 네트워크 없이 본다."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.integration import google_calendar as google
from app.shared.models import Membership, Room, User
from tests.conftest import API

CLIENT_ID = "test-client.apps.googleusercontent.com"


@pytest.fixture(autouse=True)
def 클라이언트_ID(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENT_ID)


@pytest.fixture
def 구글(monkeypatch: pytest.MonkeyPatch):
    """credential → (sub, 이름). 모르는 credential이면 틀린 토큰."""
    계정 = {"tok-a": ("sub-a", "김관객"), "tok-long": ("sub-l", "가" * 30)}

    def verify(credential: str) -> tuple[str, str]:
        if credential == "down":
            raise google.Unavailable("x")
        if credential not in 계정:
            raise google.InvalidGrant("x")
        return 계정[credential]

    monkeypatch.setattr("app.integration.google_calendar.verify_id_token", verify)


def _google(client: TestClient, credential: str):
    return client.post(f"{API}/sessions/google", json={"credential": credential})


def test_처음_오면_만들고_다시_오면_같은_사람이다(
    client: TestClient, session: Session, 구글
) -> None:
    팀장 = User(name="팀장")
    session.add(팀장)
    session.flush()
    room = Room(
        name="과제", start_date=date(2026, 11, 1), due_date=date(2026, 12, 1),
        eval_method="", member_count=4, invite_code="GOOGLE", leader_user_id=팀장.id,  # type: ignore[arg-type]
    )
    session.add(room)
    session.flush()
    session.add(Membership(room_id=room.id, user_id=팀장.id))  # type: ignore[arg-type]
    session.commit()

    res = _google(client, "tok-a")
    assert res.status_code == 201, res.text
    first = res.json()
    assert first["is_new"] is True and first["name"] == "김관객"
    me = client.get(f"{API}/me").json()
    assert me["user_id"] == first["user_id"] and me["rooms"] == []

    # 처음 한 번만 초대 코드. 다시 로그인하면 코드 없이 그 방이 보인다
    assert client.post(f"{API}/rooms/join", json={"invite_code": "GOOGLE"}).status_code == 200
    client.delete(f"{API}/sessions")
    again = _google(client, "tok-a").json()
    assert again == {**first, "is_new": False}
    assert [r["id"] for r in client.get(f"{API}/me").json()["rooms"]] == [room.id]


def test_틀린_토큰은_401(client: TestClient, session: Session, 구글) -> None:
    res = _google(client, "forged")
    assert res.status_code == 401
    assert res.json()["code"] == "UNAUTHENTICATED"
    assert session.exec(select(User)).all() == []


def test_구글이_안_받으면_503(client: TestClient, session: Session, 구글) -> None:
    res = _google(client, "down")
    assert res.status_code == 503
    assert res.json()["code"] == "GOOGLE_UNAVAILABLE"


def test_클라이언트_ID가_없으면_503(client: TestClient, monkeypatch, 구글) -> None:
    monkeypatch.delenv("GOOGLE_CLIENT_ID")
    res = _google(client, "tok-a")
    assert res.status_code == 503
    assert res.json()["code"] == "GOOGLE_NOT_CONFIGURED"


def test_긴_이름은_20자로(client: TestClient, session: Session, 구글) -> None:
    assert _google(client, "tok-long").json()["name"] == "가" * 20


def test_구글로_만든_사람은_이름으로_못_들어온다(client: TestClient, session: Session, 구글) -> None:
    _google(client, "tok-a")
    client.delete(f"{API}/sessions")
    res = client.post(f"{API}/sessions", json={"name": "김관객"})
    assert res.status_code == 404


# ── 토큰 확인 자체 ──────────────────────────────────────────────────


def _tokeninfo(monkeypatch: pytest.MonkeyPatch, status: int, body: dict) -> None:
    def fake_get(url, params=None, timeout=None):
        assert url == google.TOKENINFO_URL
        return httpx.Response(status, json=body)

    monkeypatch.setattr("app.integration.google_calendar.httpx.get", fake_get)


GOOD = {"aud": CLIENT_ID, "iss": "https://accounts.google.com", "sub": "123", "name": "진희"}


def test_맞는_토큰이면_sub와_이름(monkeypatch: pytest.MonkeyPatch) -> None:
    _tokeninfo(monkeypatch, 200, GOOD)
    assert google.verify_id_token("t") == ("123", "진희")


@pytest.mark.parametrize(
    "bad",
    [{**GOOD, "aud": "other-app"}, {**GOOD, "iss": "evil.example"}, {**GOOD, "sub": ""}],
)
def test_다른_앱이나_다른_발급처면_거절(monkeypatch: pytest.MonkeyPatch, bad: dict) -> None:
    _tokeninfo(monkeypatch, 200, bad)
    with pytest.raises(google.InvalidGrant):
        google.verify_id_token("t")


def test_구글이_400이면_틀린_토큰(monkeypatch: pytest.MonkeyPatch) -> None:
    _tokeninfo(monkeypatch, 400, {"error": "invalid_token"})
    with pytest.raises(google.InvalidGrant):
        google.verify_id_token("t")
