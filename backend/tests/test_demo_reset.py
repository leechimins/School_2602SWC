"""POST /demo/reset — 열쇠가 맞을 때만 시드로 되돌린다."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, func, select

from app.meeting.models import Scheduling
from app.shared.models import User
from tests.conftest import API

KEY = "test-reset-key"


@pytest.fixture(autouse=True)
def 열쇠(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_RESET_KEY", KEY)


def _users(db: Session) -> int:
    return db.exec(select(func.count()).select_from(User)).one()


def test_시드로_되돌리고_로그인은_그대로(client: TestClient, seeded: Session, login) -> None:
    login("지수")
    res = client.post(
        f"{API}/rooms/1/schedulings",
        json={"topic": "지워질 조율", "window_start": "2026-11-16T00:00:00+09:00",
              "window_end": "2026-11-18T23:59:00+09:00", "duration_min": 60, "mode": "any"},
    )
    assert res.status_code == 201, res.text
    before = _users(seeded)

    res = client.post(f"{API}/demo/reset", headers={"X-Demo-Key": KEY})
    assert res.status_code == 204, res.text

    seeded.expire_all()
    assert _users(seeded) == before
    topics = seeded.exec(select(Scheduling.topic)).all()
    assert "지워질 조율" not in topics
    # 번호가 시드 순서대로 다시 매겨져 쿠키가 같은 사람을 가리킨다
    me = client.get(f"{API}/me").json()
    assert me["name"] == "지수" and me["rooms"][0]["is_leader"]


@pytest.mark.parametrize("headers", [{}, {"X-Demo-Key": "wrong"}])
def test_열쇠가_없거나_틀리면_403이고_안_지운다(client: TestClient, seeded: Session, headers) -> None:
    before = _users(seeded)
    res = client.post(f"{API}/demo/reset", headers=headers)
    assert res.status_code == 403
    assert res.json()["code"] == "FORBIDDEN"
    assert _users(seeded) == before


def test_서버에_열쇠가_없으면_꺼져_있다(client: TestClient, seeded: Session, monkeypatch) -> None:
    monkeypatch.delenv("DEMO_RESET_KEY")
    res = client.post(f"{API}/demo/reset", headers={"X-Demo-Key": ""})
    assert res.status_code == 403
