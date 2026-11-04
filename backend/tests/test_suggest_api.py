"""Suggest 엔드포인트. 시드의 AI 제안 3개(10/31 회의)로 본다.

- "디자인 시안 정리" (담당자 서연)
- "최종 발표 리허설 일정 잡기" (담당자 없음)
- "시연 영상 촬영 계획" (담당자 없음, 기한 없음)
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.meeting.models import Meeting
from app.minutes.models import Task
from app.shared import demo_clock
from app.shared.base import KST
from app.shared.models import Room, User

API = "/api/v1"


def _room(session: Session) -> Room:
    return session.exec(select(Room)).one()


def _proposals(session: Session) -> list[Task]:
    return list(
        session.exec(
            select(Task).where(Task.confirmed == False).order_by(Task.id)  # noqa: E712
        ).all()
    )


def _confirmed_one(session: Session) -> Task:
    return session.exec(select(Task).where(Task.confirmed == True)).first()  # noqa: E712


def _user(session: Session, name: str) -> User:
    return session.exec(select(User).where(User.name == name)).one()


def _url(room: Room, path: str) -> str:
    return f"{API}/rooms/{room.id}/suggestions{path}"


# ── 확정 ────────────────────────────────────────────────────────────


def test_제안을_한꺼번에_확정하면_할_일이_된다(
    client: TestClient, seeded: Session, login
) -> None:
    room = _room(seeded)
    ids = [p.id for p in _proposals(seeded)]
    demo_clock.set_clock(seeded, datetime(2026, 11, 10, 18, tzinfo=KST))
    seeded.commit()
    login("민지")

    res = client.post(_url(room, "/confirm"), json={"suggestion_ids": ids})

    assert res.status_code == 200, res.text
    tasks = res.json()["tasks"]
    assert [t["id"] for t in tasks] == ids
    assert all(t["confirmed_by_name"] == "민지" for t in tasks)
    assert all(t["confirmed_at"].startswith("2026-11-10T18:00:00") for t in tasks)
    # 담당자 없이도 확정된다
    assert sum(t["assignee_user_id"] is None for t in tasks) == 2

    meeting = seeded.exec(select(Meeting).where(Meeting.topic == "중간 발표 자료 나누기")).one()
    detail = client.get(f"{API}/rooms/{room.id}/meetings/{meeting.id}").json()
    assert detail["suggestions"] == []
    assert len(detail["tasks"]) == 5 + 3


def test_이미_확정된_것이_섞이면_409이고_아무것도_확정되지_않는다(
    client: TestClient, seeded: Session, login
) -> None:
    room = _room(seeded)
    proposal = _proposals(seeded)[0]
    already = _confirmed_one(seeded)
    login("지수")

    res = client.post(
        _url(room, "/confirm"), json={"suggestion_ids": [proposal.id, already.id]}
    )

    assert res.status_code == 409
    assert res.json()["code"] == "ALREADY_CONFIRMED"
    seeded.refresh(proposal)
    assert proposal.confirmed is False


def test_같은_제안을_두_번_확정하면_두_번째는_409다(
    client: TestClient, seeded: Session, login
) -> None:
    room = _room(seeded)
    proposal = _proposals(seeded)[0]
    login("지수")

    first = client.post(_url(room, "/confirm"), json={"suggestion_ids": [proposal.id]})
    second = client.post(_url(room, "/confirm"), json={"suggestion_ids": [proposal.id]})

    assert first.status_code == 200
    assert second.status_code == 409


def test_없는_제안이나_버린_제안은_404다(
    client: TestClient, seeded: Session, login
) -> None:
    room = _room(seeded)
    proposal = _proposals(seeded)[0]
    proposal.dropped = True
    seeded.add(proposal)
    seeded.commit()
    login("지수")

    for ids in ([999999], [proposal.id]):
        res = client.post(_url(room, "/confirm"), json={"suggestion_ids": ids})
        assert res.status_code == 404


def test_빈_목록은_400이다(client: TestClient, seeded: Session, login) -> None:
    login("지수")

    res = client.post(_url(_room(seeded), "/confirm"), json={"suggestion_ids": []})

    assert res.status_code == 400
    assert res.json()["field"] == "suggestion_ids"


def test_같은_ID를_두_번_보내도_한_번만_확정된다(
    client: TestClient, seeded: Session, login
) -> None:
    room = _room(seeded)
    proposal = _proposals(seeded)[0]
    login("지수")

    res = client.post(
        _url(room, "/confirm"), json={"suggestion_ids": [proposal.id, proposal.id]}
    )

    assert res.status_code == 200
    assert len(res.json()["tasks"]) == 1


def test_팀원이_아니면_확정할_수_없다(
    client: TestClient, seeded: Session, login
) -> None:
    seeded.add(User(name="밖사람"))
    seeded.commit()
    login("밖사람")

    res = client.post(
        _url(_room(seeded), "/confirm"),
        json={"suggestion_ids": [_proposals(seeded)[0].id]},
    )

    assert res.status_code == 403


# ── 고치기 ──────────────────────────────────────────────────────────


def test_제안의_제목_담당자_기한을_고친다(
    client: TestClient, seeded: Session, login
) -> None:
    room = _room(seeded)
    proposal = _proposals(seeded)[1]  # 담당자 없음
    hyunwoo = _user(seeded, "현우")
    login("서연")

    res = client.patch(
        _url(room, f"/{proposal.id}"),
        json={
            "title": "리허설 날짜 정하기",
            "assignee_user_id": hyunwoo.id,
            "due_date": "2026-11-20",
        },
    )

    assert res.status_code == 200, res.text
    assert res.json() == {
        "id": proposal.id,
        "title": "리허설 날짜 정하기",
        "due_date": "2026-11-20",
        "assignee_user_id": hyunwoo.id,
        "assignee_name": "현우",
    }


def test_보낸_칸만_바뀌고_null은_비운다(
    client: TestClient, seeded: Session, login
) -> None:
    room = _room(seeded)
    proposal = _proposals(seeded)[0]  # 담당자 서연, 기한 11/14
    login("지수")

    body = client.patch(
        _url(room, f"/{proposal.id}"), json={"assignee_user_id": None}
    ).json()

    assert body["assignee_user_id"] is None
    assert body["title"] == "디자인 시안 정리"
    assert body["due_date"] == date(2026, 11, 14).isoformat()


def test_팀원이_아닌_사람은_담당자가_될_수_없다(
    client: TestClient, seeded: Session, login
) -> None:
    room = _room(seeded)
    outsider = User(name="밖사람")
    seeded.add(outsider)
    seeded.commit()
    login("지수")

    res = client.patch(
        _url(room, f"/{_proposals(seeded)[0].id}"),
        json={"assignee_user_id": outsider.id},
    )

    assert res.status_code == 400
    assert res.json()["field"] == "assignee_user_id"


def test_제목은_비울_수_없다(client: TestClient, seeded: Session, login) -> None:
    login("지수")

    res = client.patch(
        _url(_room(seeded), f"/{_proposals(seeded)[0].id}"), json={"title": None}
    )

    assert res.status_code == 400
    assert res.json()["field"] == "title"


def test_확정된_할_일은_제안으로_고칠_수_없다(
    client: TestClient, seeded: Session, login
) -> None:
    login("지수")

    res = client.patch(
        _url(_room(seeded), f"/{_confirmed_one(seeded).id}"), json={"title": "바꿈"}
    )

    assert res.status_code == 409


# ── 버리기 ──────────────────────────────────────────────────────────


def test_제안을_버리면_행은_남고_회의록에서_빠진다(
    client: TestClient, seeded: Session, login
) -> None:
    room = _room(seeded)
    proposal = _proposals(seeded)[2]
    login("현우")

    res = client.delete(_url(room, f"/{proposal.id}"))

    assert res.status_code == 204
    seeded.refresh(proposal)
    assert proposal.dropped is True
    meetings = client.get(f"{API}/rooms/{room.id}/meetings").json()["meetings"]
    assert meetings[0]["suggestion_count"] == 2


def test_버린_제안을_또_버리면_404다(
    client: TestClient, seeded: Session, login
) -> None:
    room = _room(seeded)
    proposal = _proposals(seeded)[2]
    login("지수")

    client.delete(_url(room, f"/{proposal.id}"))
    res = client.delete(_url(room, f"/{proposal.id}"))

    assert res.status_code == 404


def test_확정된_할_일은_제안으로_버릴_수_없다(
    client: TestClient, seeded: Session, login
) -> None:
    login("지수")

    res = client.delete(_url(_room(seeded), f"/{_confirmed_one(seeded).id}"))

    assert res.status_code == 409
