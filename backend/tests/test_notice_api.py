"""알림 — 만드는 emit()과 읽는 두 엔드포인트.

emit()은 레인 B가 부르는 함수다. 할 일 상태가 바뀔 때 알림을 만드는 유일한
길이라, 중복을 막는 규칙이 여기서 깨지면 알림함이 같은 카드로 찬다.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.main import app
from app.minutes.models import Task
from app.notice.models import Notification
from app.shared.db import session_dep
from app.shared.enums import NotificationKind, TaskOrigin, TaskState
from app.shared.models import Membership, Room, User
from app.shared.notify import emit

API = "/api/v1"


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[session_dep] = lambda: session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class 팀:
    def __init__(self, room_id: int, 지수: int, 민지: int, 현우: int) -> None:
        self.room_id = room_id
        self.지수 = 지수
        self.민지 = 민지
        self.현우 = 현우

    @property
    def 전원(self) -> list[int]:
        return [self.지수, self.민지, self.현우]


@pytest.fixture
def 방(session: Session) -> 팀:
    사람들 = [User(name=이름) for 이름 in ("지수", "민지", "현우")]
    session.add_all(사람들)
    session.flush()
    ids = [u.id for u in 사람들]
    assert all(i is not None for i in ids)

    room = Room(
        name="서비스디자인 팀 프로젝트",
        start_date=date(2026, 10, 20),
        due_date=date(2026, 12, 11),
        eval_method="최종 발표 + 시연",
        member_count=3,
        invite_code="T9K2QM",
        leader_user_id=ids[0],  # type: ignore[arg-type]
    )
    session.add(room)
    session.flush()
    assert room.id is not None

    session.add_all(
        [Membership(room_id=room.id, user_id=uid) for uid in ids]  # type: ignore[arg-type]
    )
    session.commit()
    return 팀(room.id, *ids)  # type: ignore[arg-type]


def _login(client: TestClient, name: str) -> None:
    assert client.post(f"{API}/sessions", json={"name": name}).status_code == 201


def _emit_blocked(session: Session, 방: 팀, *, dedupe: str = "task42") -> int:
    return emit(
        session,
        room_id=방.room_id,
        user_ids=[방.지수, 방.민지],  # 막힌 현우 본인은 뺀다
        kind=NotificationKind.BLOCKED,
        reason="현우가 막혔다고 표시했습니다",
        dedupe=dedupe,
    )


# ── emit() ──────────────────────────────────────────────────────────


def test_사람마다_한_장씩_생긴다(session: Session, 방: 팀) -> None:
    assert _emit_blocked(session, 방) == 2
    session.commit()

    rows = session.exec(select(Notification)).all()
    assert {r.user_id for r in rows} == {방.지수, 방.민지}
    assert all(r.reason == "현우가 막혔다고 표시했습니다" for r in rows)
    assert all(r.read_at is None for r in rows)


def test_같은_일로_두_번_불러도_한_장이다(session: Session, 방: 팀) -> None:
    """기한이 지난 할 일은 서버가 볼 때마다 늦음이다. 그때마다 만들면
    알림함이 같은 카드로 찬다.
    """
    assert _emit_blocked(session, 방) == 2
    assert _emit_blocked(session, 방) == 0  # 새로 만든 게 없다
    session.commit()

    assert len(session.exec(select(Notification)).all()) == 2


def test_상황이_바뀌면_다시_뜬다(session: Session, 방: 팀) -> None:
    """기한이 밀리면 늦음 알림은 다시 떠야 한다."""
    emit(
        session,
        room_id=방.room_id,
        user_ids=[방.지수],
        kind=NotificationKind.LATE,
        reason="기한이 지났는데 끝나지 않았습니다",
        dedupe="task42:due20261120",
    )
    새로 = emit(
        session,
        room_id=방.room_id,
        user_ids=[방.지수],
        kind=NotificationKind.LATE,
        reason="기한이 지났는데 끝나지 않았습니다",
        dedupe="task42:due20261127",  # 기한이 밀렸다
    )
    assert 새로 == 1
    session.commit()
    assert len(session.exec(select(Notification)).all()) == 2


def test_종류가_다르면_같은_할_일도_따로_뜬다(session: Session, 방: 팀) -> None:
    """부르는 쪽이 dedupe를 둘 다 "task42"로만 적어도 섞이지 않아야 한다 —
    emit이 앞에 kind를 붙이는 이유다.
    """
    for kind in (NotificationKind.BLOCKED, NotificationKind.DONE):
        emit(
            session,
            room_id=방.room_id,
            user_ids=[방.지수],
            kind=kind,
            reason="상태가 바뀌었습니다",
            dedupe="task42",
        )
    session.commit()

    rows = session.exec(select(Notification)).all()
    assert {r.kind for r in rows} == {NotificationKind.BLOCKED, NotificationKind.DONE}


def test_받을_사람이_없으면_아무_일도_안_한다(session: Session, 방: 팀) -> None:
    assert (
        emit(
            session,
            room_id=방.room_id,
            user_ids=[],
            kind=NotificationKind.DONE,
            reason="x",
            dedupe="task1",
        )
        == 0
    )


def test_할_일을_가리킬_수_있다(session: Session, 방: 팀) -> None:
    """task_id에 FK가 걸려 있다. 레인 B의 테이블이라 둘이 붙는지 본다."""
    task = Task(
        room_id=방.room_id,
        title="설문 문항 정리",
        state=TaskState.BLOCKED,
        origin=TaskOrigin.AI,
        confirmed=True,
        confirmed_by=방.지수,
        confirmed_at=date.today(),  # type: ignore[arg-type]
    )
    session.add(task)
    session.flush()

    emit(
        session,
        room_id=방.room_id,
        user_ids=[방.지수],
        kind=NotificationKind.BLOCKED,
        reason="현우가 막혔다고 표시했습니다",
        dedupe=f"task{task.id}",
        task_id=task.id,
    )
    session.commit()
    assert session.exec(select(Notification)).one().task_id == task.id


# ── 목록과 읽음 ──────────────────────────────────────────────────────


def test_로그인_없이는_못_읽는다(client: TestClient, 방: 팀) -> None:
    assert client.get(f"{API}/rooms/{방.room_id}/notifications").status_code == 401


def test_팀원이_아니면_못_읽는다(
    client: TestClient, session: Session, 방: 팀
) -> None:
    남 = User(name="남의팀사람")
    session.add(남)
    session.commit()

    _login(client, "남의팀사람")
    res = client.get(f"{API}/rooms/{방.room_id}/notifications")
    assert res.status_code == 403
    assert res.json()["code"] == "FORBIDDEN"


def test_알림이_없으면_빈_목록이다(client: TestClient, 방: 팀) -> None:
    """빈 화면에 "좋은 상태"를 쓰려면 404가 아니라 빈 목록이어야 한다."""
    _login(client, "지수")
    res = client.get(f"{API}/rooms/{방.room_id}/notifications")
    assert res.status_code == 200
    assert res.json() == {"items": [], "unread_count": 0}


def test_내_알림만_보인다(client: TestClient, session: Session, 방: 팀) -> None:
    _emit_blocked(session, 방)  # 지수·민지에게
    session.commit()

    _login(client, "현우")
    assert client.get(f"{API}/rooms/{방.room_id}/notifications").json() == {
        "items": [],
        "unread_count": 0,
    }

    client.delete(f"{API}/sessions")
    _login(client, "지수")
    body = client.get(f"{API}/rooms/{방.room_id}/notifications").json()
    assert len(body["items"]) == 1
    assert body["unread_count"] == 1
    assert body["items"][0]["kind"] == "blocked"
    assert body["items"][0]["reason"] == "현우가 막혔다고 표시했습니다"


def test_모두_읽음_처리(client: TestClient, session: Session, 방: 팀) -> None:
    for i in range(3):
        emit(
            session,
            room_id=방.room_id,
            user_ids=[방.지수],
            kind=NotificationKind.LATE,
            reason="기한이 지났습니다",
            dedupe=f"task{i}",
        )
    session.commit()

    _login(client, "지수")
    assert client.get(f"{API}/rooms/{방.room_id}/notifications").json()["unread_count"] == 3

    res = client.post(f"{API}/rooms/{방.room_id}/notifications/read", json={})
    assert res.status_code == 200
    assert res.json() == {"unread_count": 0}

    # 읽은 카드는 사라지지 않는다 — 방금 읽은 것이 없어지면 오류처럼 보인다.
    body = client.get(f"{API}/rooms/{방.room_id}/notifications").json()
    assert len(body["items"]) == 3
    assert all(item["read_at"] is not None for item in body["items"])


def test_하나만_읽음_처리(client: TestClient, session: Session, 방: 팀) -> None:
    for i in range(3):
        emit(
            session,
            room_id=방.room_id,
            user_ids=[방.지수],
            kind=NotificationKind.LATE,
            reason="기한이 지났습니다",
            dedupe=f"task{i}",
        )
    session.commit()

    _login(client, "지수")
    목록 = client.get(f"{API}/rooms/{방.room_id}/notifications").json()["items"]

    res = client.post(
        f"{API}/rooms/{방.room_id}/notifications/read", json={"ids": [목록[0]["id"]]}
    )
    assert res.json() == {"unread_count": 2}


def test_남의_알림은_ids에_넣어도_안_바뀐다(
    client: TestClient, session: Session, 방: 팀
) -> None:
    _emit_blocked(session, 방)  # 지수·민지에게
    session.commit()
    민지_것 = session.exec(
        select(Notification).where(Notification.user_id == 방.민지)
    ).one()

    _login(client, "지수")
    res = client.post(
        f"{API}/rooms/{방.room_id}/notifications/read", json={"ids": [민지_것.id]}
    )
    assert res.status_code == 200

    session.expire_all()
    assert session.get(Notification, 민지_것.id).read_at is None  # type: ignore[union-attr]
