"""공백만 넣은 제목·주제·방 이름은 400으로 거절하고, 앞뒤 공백은 잘라 저장한다.

min_length=1은 공백도 글자로 세서 "   "가 그대로 저장되고 목록에 빈 행이 생겼다.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.minutes.models import Task
from app.shared.models import Room

API = "/api/v1"

NEW_ROOM = {
    "name": "캡스톤 디자인",
    "description": "학기 프로젝트",
    "start_date": "2026-11-01",
    "due_date": "2026-12-20",
    "member_count": 3,
}


def _room(session: Session) -> Room:
    return session.exec(select(Room)).one()


def _proposal(session: Session) -> Task:
    return session.exec(
        select(Task).where(Task.confirmed == False).order_by(Task.id)  # noqa: E712
    ).first()


def _confirmed(session: Session) -> Task:
    return session.exec(
        select(Task).where(Task.confirmed == True).order_by(Task.id)  # noqa: E712
    ).first()


# 각 경우: (field, 글자를 넣어 보내고 응답을 돌려주는 함수, 저장된 값을 읽는 응답 키)
Send = Callable[[TestClient, Session, str], "object"]


def _create_room(client: TestClient, session: Session, value: str):
    return client.post(f"{API}/rooms", json=NEW_ROOM | {"name": value})


def _start_record(client: TestClient, session: Session, value: str):
    room = _room(session)
    return client.post(f"{API}/rooms/{room.id}/meetings", json={"topic": value})


def _create_task(client: TestClient, session: Session, value: str):
    room = _room(session)
    return client.post(f"{API}/rooms/{room.id}/tasks", json={"title": value})


def _edit_task(client: TestClient, session: Session, value: str):
    room, task = _room(session), _confirmed(session)
    return client.patch(f"{API}/rooms/{room.id}/tasks/{task.id}", json={"title": value})


def _edit_suggestion(client: TestClient, session: Session, value: str):
    room, proposal = _room(session), _proposal(session)
    return client.patch(
        f"{API}/rooms/{room.id}/suggestions/{proposal.id}", json={"title": value}
    )


CASES = [
    pytest.param(_create_room, "name", "name", id="방 이름"),
    pytest.param(_start_record, "topic", "topic", id="기록 시작 주제"),
    pytest.param(_create_task, "title", "title", id="할 일 직접 추가"),
    pytest.param(_edit_task, "title", "title", id="할 일 고치기"),
    pytest.param(_edit_suggestion, "title", "title", id="제안 고치기"),
]


@pytest.mark.parametrize(("send", "field", "key"), CASES)
@pytest.mark.parametrize("blank", ["   ", "\t\n "])
def test_공백만_넣으면_400이다(
    client: TestClient, seeded: Session, login, send, field, key, blank
) -> None:
    login("지수")

    res = send(client, seeded, blank)

    assert res.status_code == 400, res.text
    assert (res.json()["code"], res.json()["field"]) == ("INVALID_INPUT", field)


@pytest.mark.parametrize(("send", "field", "key"), CASES)
def test_앞뒤_공백은_잘라_저장한다(
    client: TestClient, seeded: Session, login, send, field, key
) -> None:
    login("지수")

    res = send(client, seeded, "  발표 대본 쓰기  ")

    assert res.status_code in (200, 201), res.text
    assert res.json()[key] == "발표 대본 쓰기"
