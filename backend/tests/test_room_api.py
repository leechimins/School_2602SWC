"""Room 엔드포인트. 로그인부터 실제 요청으로 본다.

시드(서비스디자인 팀, 지수 팀장, 현우 누적 양보 3)를 깔고 시작한다.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select

from app.room.router import join_room
from app.room.schemas import JoinIn
from app.room.service import INVITE_ALPHABET
from app.shared import demo_clock
from app.shared.base import KST
from app.shared.models import Membership, Room, User
from tools.seed import INVITE_CODE

API = "/api/v1"

NEW_ROOM = {
    "name": "캡스톤 디자인",
    "description": "학기 프로젝트",
    "start_date": "2026-11-01",
    "due_date": "2026-12-20",
    "eval_method": "발표",
    "member_count": 3,
}


def _seed_room(session: Session) -> Room:
    return session.exec(select(Room).where(Room.invite_code == INVITE_CODE)).one()


def _new_user(session: Session, name: str) -> User:
    user = User(name=name)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _all_keys(value) -> set[str]:
    """응답 JSON 안의 모든 키. 남의 점수 칸이 섞였는지 보려고 쓴다."""
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _all_keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _all_keys(v)}
    return set()


# ── GET /me ─────────────────────────────────────────────────────────


def test_로그인_없이는_내_계정을_못_본다(client: TestClient, seeded) -> None:
    assert client.get(f"{API}/me").status_code == 401


def test_내_계정에_속한_방과_팀장_여부가_온다(client: TestClient, seeded, login) -> None:
    login("지수")

    body = client.get(f"{API}/me").json()

    assert body["name"] == "지수"
    assert [(r["name"], r["is_leader"]) for r in body["rooms"]] == [
        ("서비스디자인 팀 프로젝트", True)
    ]


def test_방이_없어도_내_계정은_200이다(
    client: TestClient, session: Session, login
) -> None:
    _new_user(session, "새사람")
    login("새사람")

    res = client.get(f"{API}/me")

    assert res.status_code == 200
    assert res.json()["rooms"] == []


# ── GET /rooms/{id} ─────────────────────────────────────────────────


def test_방_정보에_팀원과_양보_단계가_온다(
    client: TestClient, seeded: Session, login
) -> None:
    room = _seed_room(seeded)
    login("민지")

    body = client.get(f"{API}/rooms/{room.id}").json()

    levels = {m["name"]: m["yield_level"] for m in body["members"]}
    assert levels == {"지수": "none", "민지": "none", "현우": "much", "서연": "none"}
    assert body["members"][0]["name"] == "지수"  # 팀장이 맨 위
    assert body["members"][0]["is_leader"] is True
    assert [m["name"] for m in body["members"] if m["is_me"]] == ["민지"]
    assert body["joined_count"] == 4


def test_방_정보에_누적_양보_숫자가_없다(
    client: TestClient, seeded: Session, login
) -> None:
    """남의 점수는 응답에 담지 않는다 — 제품의 핵심 약속."""
    room = _seed_room(seeded)
    login("지수")

    keys = _all_keys(client.get(f"{API}/rooms/{room.id}").json())

    assert "yield_total" not in keys
    assert not any("score" in k or "points" in k for k in keys)


def test_조율_시작_권한은_팀장만_참이다(
    client: TestClient, seeded: Session, login
) -> None:
    room = _seed_room(seeded)

    login("지수")
    assert client.get(f"{API}/rooms/{room.id}").json()["can_start_scheduling"] is True

    login("현우")
    assert client.get(f"{API}/rooms/{room.id}").json()["can_start_scheduling"] is False


def test_디데이는_시연_시계의_오늘_기준이다(
    client: TestClient, seeded: Session, login
) -> None:
    room = _seed_room(seeded)
    demo_clock.set_clock(seeded, datetime(2026, 11, 10, 9, tzinfo=KST))
    seeded.commit()
    login("지수")

    body = client.get(f"{API}/rooms/{room.id}").json()

    assert body["d_day"] == 31  # 11/10 → 12/11


def test_팀원이_아니면_방_정보를_못_본다(
    client: TestClient, seeded: Session, login
) -> None:
    room = _seed_room(seeded)
    _new_user(seeded, "밖사람")
    login("밖사람")

    res = client.get(f"{API}/rooms/{room.id}")

    assert res.status_code == 403
    assert res.json()["code"] == "FORBIDDEN"


# ── POST /rooms ─────────────────────────────────────────────────────


def test_방을_만들면_만든_사람이_팀장이고_초대_코드가_나온다(
    client: TestClient, session: Session, login
) -> None:
    user = _new_user(session, "새팀장")
    login("새팀장")

    res = client.post(f"{API}/rooms", json=NEW_ROOM)

    assert res.status_code == 201, res.text
    body = res.json()
    assert body["leader_user_id"] == user.id
    assert body["can_start_scheduling"] is True
    assert [m["name"] for m in body["members"]] == ["새팀장"]
    assert len(body["invite_code"]) == 6
    assert set(body["invite_code"]) <= set(INVITE_ALPHABET)


def test_평가_방식_없이도_방을_만든다(
    client: TestClient, session: Session, login
) -> None:
    """11/4 브리프에서 화면의 평가 방식 칸이 빠졌다. 안 보내도 400이 아니다."""
    _new_user(session, "새팀장")
    login("새팀장")
    body = {k: v for k, v in NEW_ROOM.items() if k != "eval_method"}

    res = client.post(f"{API}/rooms", json=body)

    assert res.status_code == 201, res.text
    assert res.json()["eval_method"] == ""


def test_초대_코드가_겹치면_다시_뽑는다(
    client: TestClient, seeded: Session, login, monkeypatch
) -> None:
    """첫 코드를 시드 방의 코드와 같게 만들어 유일 제약에 걸리게 한다."""
    codes = iter([INVITE_CODE, "NEWCDE"])
    monkeypatch.setattr("app.room.router.new_invite_code", lambda: next(codes))
    _new_user(seeded, "새팀장")
    login("새팀장")

    res = client.post(f"{API}/rooms", json=NEW_ROOM)

    assert res.status_code == 201, res.text
    assert res.json()["invite_code"] == "NEWCDE"
    # 겹친 첫 시도가 남긴 방이 없다
    assert len(seeded.exec(select(Room)).all()) == 2


def test_마감일이_시작일보다_앞서면_400이다(
    client: TestClient, session: Session, login
) -> None:
    _new_user(session, "새팀장")
    login("새팀장")

    res = client.post(
        f"{API}/rooms", json={**NEW_ROOM, "start_date": "2026-12-21"}
    )

    assert res.status_code == 400
    assert res.json()["field"] == "due_date"


def test_팀원_수는_2명에서_6명이다(
    client: TestClient, session: Session, login
) -> None:
    _new_user(session, "새팀장")
    login("새팀장")

    for count in (1, 7):
        res = client.post(f"{API}/rooms", json={**NEW_ROOM, "member_count": count})
        assert res.status_code == 400
        assert res.json()["field"] == "member_count"


def test_로그인_없이는_방을_못_만든다(client: TestClient, seeded) -> None:
    assert client.post(f"{API}/rooms", json=NEW_ROOM).status_code == 401


# ── POST /rooms/join · 미리보기 ──────────────────────────────────────


def _make_room(client: TestClient, session: Session, login, leader: str) -> str:
    _new_user(session, leader)
    login(leader)
    return client.post(f"{API}/rooms", json=NEW_ROOM).json()["invite_code"]


def test_초대_코드로_들어가면_팀원이_된다(
    client: TestClient, session: Session, login
) -> None:
    code = _make_room(client, session, login, "새팀장")
    joiner = _new_user(session, "새팀원")
    login("새팀원")

    res = client.post(f"{API}/rooms/join", json={"invite_code": code.lower()})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["joined_count"] == 2
    assert body["can_start_scheduling"] is False
    assert session.exec(
        select(Membership).where(Membership.user_id == joiner.id)
    ).first()


def test_같은_방에_두_번_들어가면_409다(
    client: TestClient, session: Session, login
) -> None:
    code = _make_room(client, session, login, "새팀장")

    res = client.post(f"{API}/rooms/join", json={"invite_code": code})

    assert res.status_code == 409
    assert res.json()["code"] == "ALREADY_MEMBER"


def test_정원이_찬_방에는_못_들어간다(
    client: TestClient, seeded: Session, login
) -> None:
    """시드 방은 정원 4명에 4명이 다 들어와 있다."""
    _new_user(seeded, "다섯째")
    login("다섯째")

    res = client.post(f"{API}/rooms/join", json={"invite_code": INVITE_CODE})

    assert res.status_code == 409
    assert res.json()["code"] == "ROOM_FULL"


def test_들어가기는_방_행을_잠그고_정원을_센다(
    seeded: Session, test_engine: Engine
) -> None:
    """마지막 자리에 둘이 동시에 들어오면 정원을 넘을 수 있었다.

    한 연결이 방 행을 잡고 있는 동안 다른 연결의 들어가기는 기다려야 한다.
    TestClient는 세션 하나를 공유해 동시 요청을 못 만들므로 연결 둘로 본다.
    """
    joiner = _new_user(seeded, "다섯째")
    seeded.commit()
    first = Session(test_engine)
    second = Session(test_engine)
    try:
        first.exec(select(Room).where(Room.invite_code == INVITE_CODE).with_for_update()).one()
        second.exec(text("SET LOCAL lock_timeout = '300ms'"))
        with pytest.raises(OperationalError):
            join_room(JoinIn(invite_code=INVITE_CODE), user_id=joiner.id, db=second)
    finally:
        second.rollback()
        first.rollback()
        second.close()
        first.close()


def test_없는_초대_코드는_404다(client: TestClient, seeded, login) -> None:
    login("지수")

    assert client.post(f"{API}/rooms/join", json={"invite_code": "ZZZZZZ"}).status_code == 404
    assert client.get(f"{API}/rooms/by-invite-code/ZZZZZZ").status_code == 404


def test_미리보기는_방_이름과_인원만_준다(client: TestClient, seeded, login) -> None:
    login("지수")

    body = client.get(f"{API}/rooms/by-invite-code/{INVITE_CODE}").json()

    assert body == {
        "name": "서비스디자인 팀 프로젝트",
        "member_count": 4,
        "joined_count": 4,
    }
