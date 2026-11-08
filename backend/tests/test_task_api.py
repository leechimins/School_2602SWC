"""Task 엔드포인트와 할 일 알림 3종. 시드의 할 일로 본다.

확정된 할 일 (시연 시계 오늘 = 11/10 기준):
- 사용자 인터뷰 정리 — 지수, 진행 중, 기한 11/8 → 늦음
- 발표 슬라이드 초안 — 민지, 시작 전, 11/13
- 프로토타입 화면 구현 — 현우, 막힘, 11/15
- 참고 사례 조사 — 지수, 완료, 11/5 (완료라 늦음 아님)
- 발표 대본 작성 — 담당자 없음, 시작 전, 11/17
- 대면 회의 장소 예약 — 지수, 시작 전, 11/12, 직접 추가
그 밖에 확정 전 AI 제안 3개.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.minutes.models import Task
from app.notice.models import Notification
from app.shared import demo_clock
from app.shared.base import KST
from app.shared.enums import NotificationKind
from app.shared.models import Room, User

API = "/api/v1"


@pytest.fixture
def room(seeded: Session) -> Room:
    """시연 시계를 11/10 18시에 둔다."""
    demo_clock.set_clock(seeded, datetime(2026, 11, 10, 18, tzinfo=KST))
    seeded.commit()
    return seeded.exec(select(Room)).one()


def _url(room: Room, path: str = "") -> str:
    return f"{API}/rooms/{room.id}/tasks{path}"


def _task(session: Session, title: str) -> Task:
    return session.exec(select(Task).where(Task.title == title)).one()


def _user(session: Session, name: str) -> User:
    return session.exec(select(User).where(User.name == name)).one()


def _notes(session: Session, kind: NotificationKind, task: Task) -> list[Notification]:
    return list(
        session.exec(
            select(Notification).where(
                Notification.kind == kind, Notification.task_id == task.id
            )
        ).all()
    )


# ── 팀 할 일 ────────────────────────────────────────────────────────


def test_팀_할_일은_담당자_없음_나_다른_사람_순이다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    login("지수")

    titles = [t["title"] for t in client.get(_url(room)).json()["tasks"]]

    assert titles == [
        "발표 대본 작성",  # 담당자 없음
        "참고 사례 조사",  # 나(지수), 기한 순
        "사용자 인터뷰 정리",
        "대면 회의 장소 예약",
        "발표 슬라이드 초안",  # 민지
        "프로토타입 화면 구현",  # 현우
    ]


def test_확정_전_제안은_목록에_없고_수만_온다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    login("지수")

    body = client.get(_url(room)).json()

    assert body["suggestion_count"] == 3
    assert "디자인 시안 정리" not in [t["title"] for t in body["tasks"]]


def test_늦음은_기한이_지났고_완료가_아닌_것만이다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    login("지수")

    late = [t["title"] for t in client.get(_url(room)).json()["tasks"] if t["is_late"]]

    assert late == ["사용자 인터뷰 정리"]


def test_사람별_남은_할_일_수에서_완료는_빠진다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    login("민지")

    counts = {c["name"]: c["remaining"] for c in client.get(_url(room)).json()["task_counts"]}

    assert counts == {"지수": 2, "민지": 1, "현우": 1, "서연": 0}


def test_상태와_담당자로_거른다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    login("지수")
    minji = _user(seeded, "민지")

    def titles(params: str) -> list[str]:
        return [t["title"] for t in client.get(_url(room, f"?{params}")).json()["tasks"]]

    assert titles("state=blocked") == ["프로토타입 화면 구현"]
    assert titles("unassigned=true") == ["발표 대본 작성"]
    assert titles(f"assignee_user_id={minji.id}") == ["발표 슬라이드 초안"]


def test_출처는_회의_날짜와_주제이고_직접_추가는_null이다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    login("지수")

    by_title = {t["title"]: t for t in client.get(_url(room)).json()["tasks"]}

    assert by_title["사용자 인터뷰 정리"]["source"] == {
        "meeting_id": by_title["사용자 인터뷰 정리"]["source"]["meeting_id"],
        "held_on": "2026-10-31",
        "topic": "중간 발표 자료 나누기",
    }
    assert by_title["대면 회의 장소 예약"]["source"] is None


def test_상태_변경_권한은_담당자이고_담당자_없으면_전원이다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    login("지수")

    perms = {t["title"]: t["can_change_status"] for t in client.get(_url(room)).json()["tasks"]}

    assert perms["사용자 인터뷰 정리"] is True  # 내 것
    assert perms["발표 대본 작성"] is True  # 담당자 없음
    assert perms["발표 슬라이드 초안"] is False  # 민지 것


def test_팀원이_아니면_못_본다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    seeded.add(User(name="밖사람"))
    seeded.commit()
    login("밖사람")

    assert client.get(_url(room)).status_code == 403


# ── 내 할 일 · 하나 보기 ────────────────────────────────────────────


def test_내_할_일은_기한_순이다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    login("지수")

    titles = [t["title"] for t in client.get(_url(room, "/mine")).json()["tasks"]]

    assert titles == ["참고 사례 조사", "사용자 인터뷰 정리", "대면 회의 장소 예약"]


def test_제안은_할_일로_조회되지_않는다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    login("지수")
    proposal = _task(seeded, "디자인 시안 정리")

    assert client.get(_url(room, f"/{proposal.id}")).status_code == 404


# ── 상태 변경과 막힘·완료 알림 ──────────────────────────────────────


def test_담당자가_아니면_상태를_못_바꾼다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    task = _task(seeded, "발표 슬라이드 초안")  # 민지 것
    login("지수")

    res = client.patch(_url(room, f"/{task.id}/status"), json={"state": "doing"})

    assert res.status_code == 403
    assert res.json()["code"] == "NOT_ASSIGNEE"


def test_담당자_없는_할_일은_누구나_상태를_바꾼다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    task = _task(seeded, "발표 대본 작성")
    login("서연")

    res = client.patch(_url(room, f"/{task.id}/status"), json={"state": "doing"})

    assert res.status_code == 200
    assert res.json()["state"] == "doing"


def test_막힘으로_바꾸면_나머지_팀원에게_알림이_간다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    task = _task(seeded, "발표 슬라이드 초안")
    minji = _user(seeded, "민지")
    login("민지")

    client.patch(_url(room, f"/{task.id}/status"), json={"state": "blocked"})

    notes = _notes(seeded, NotificationKind.BLOCKED, task)
    assert len(notes) == 3
    assert minji.id not in {n.user_id for n in notes}
    assert "민지님이 '발표 슬라이드 초안'에서 막혔다고" in notes[0].reason


def test_같은_상태를_다시_보내면_알림이_더_생기지_않는다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    task = _task(seeded, "발표 슬라이드 초안")
    login("민지")

    client.patch(_url(room, f"/{task.id}/status"), json={"state": "blocked"})
    client.patch(_url(room, f"/{task.id}/status"), json={"state": "blocked"})

    assert len(_notes(seeded, NotificationKind.BLOCKED, task)) == 3


def test_풀렸다가_다시_막히면_다시_알린다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    task = _task(seeded, "발표 슬라이드 초안")
    login("민지")

    client.patch(_url(room, f"/{task.id}/status"), json={"state": "blocked"})
    client.patch(_url(room, f"/{task.id}/status"), json={"state": "doing"})
    demo_clock.set_clock(seeded, datetime(2026, 11, 11, 9, tzinfo=KST))
    seeded.commit()
    client.patch(_url(room, f"/{task.id}/status"), json={"state": "blocked"})

    assert len(_notes(seeded, NotificationKind.BLOCKED, task)) == 6


def test_시계를_멈춰_둬도_다시_막히면_다시_알린다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    """시연 중에는 시계를 멈춰 둔다. 시계 시각이 같아도 두 번째 막힘이 가야 한다."""
    task = _task(seeded, "발표 슬라이드 초안")
    login("민지")

    client.patch(_url(room, f"/{task.id}/status"), json={"state": "blocked"})
    client.patch(_url(room, f"/{task.id}/status"), json={"state": "doing"})
    client.patch(_url(room, f"/{task.id}/status"), json={"state": "blocked"})

    assert len(_notes(seeded, NotificationKind.BLOCKED, task)) == 6


def test_완료로_바꾸면_완료_알림이_간다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    task = _task(seeded, "프로토타입 화면 구현")
    login("현우")

    client.patch(_url(room, f"/{task.id}/status"), json={"state": "done"})

    notes = _notes(seeded, NotificationKind.DONE, task)
    assert len(notes) == 3
    assert "현우님이 '프로토타입 화면 구현' 할 일을 완료했습니다." == notes[0].reason


# ── 늦음 알림 ───────────────────────────────────────────────────────


def test_조회하면_늦은_할_일에_늦음_알림이_한_번만_생긴다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    task = _task(seeded, "사용자 인터뷰 정리")
    jisu = _user(seeded, "지수")
    login("민지")

    client.get(_url(room))
    client.get(_url(room))

    notes = _notes(seeded, NotificationKind.LATE, task)
    assert [n.user_id for n in notes] == [jisu.id]  # 담당자에게만
    assert notes[0].reason == "'사용자 인터뷰 정리' 기한(11/8)이 지났습니다."


def test_시계가_기한_전이면_늦음_알림이_없다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    demo_clock.set_clock(seeded, datetime(2026, 11, 4, 9, tzinfo=KST))
    seeded.commit()
    login("지수")

    client.get(_url(room))

    assert seeded.exec(
        select(Notification).where(Notification.kind == NotificationKind.LATE)
    ).all() == []


def test_기한을_바꾸면_늦음_알림이_다시_뜬다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    task = _task(seeded, "사용자 인터뷰 정리")
    login("지수")

    client.get(_url(room))
    client.patch(_url(room, f"/{task.id}"), json={"due_date": "2026-11-09"})
    client.get(_url(room, "/mine"))

    assert len(_notes(seeded, NotificationKind.LATE, task)) == 2


def test_담당자_없는_할_일이_늦으면_팀원_전원에게_간다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    task = _task(seeded, "발표 대본 작성")
    login("지수")
    client.patch(_url(room, f"/{task.id}"), json={"due_date": "2026-11-09"})

    client.get(_url(room))

    assert len(_notes(seeded, NotificationKind.LATE, task)) == 4


# ── 고치기 · 넘기기 · 필요 없음 · 직접 추가 ─────────────────────────


def test_내용은_팀원_누구나_고친다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    task = _task(seeded, "발표 슬라이드 초안")  # 민지 것
    login("현우")

    res = client.patch(_url(room, f"/{task.id}"), json={"title": "발표 슬라이드 1차"})

    assert res.status_code == 200
    assert res.json()["title"] == "발표 슬라이드 1차"


def test_팀원이_아닌_담당자와_빈_제목은_400이다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    task = _task(seeded, "발표 슬라이드 초안")
    outsider = User(name="밖사람")
    seeded.add(outsider)
    seeded.commit()
    login("지수")

    bad_assignee = client.patch(
        _url(room, f"/{task.id}"), json={"assignee_user_id": outsider.id}
    )
    empty_title = client.patch(_url(room, f"/{task.id}"), json={"title": None})

    assert bad_assignee.json()["field"] == "assignee_user_id"
    assert empty_title.json()["field"] == "title"


def test_담당자를_넘기면_권한도_따라간다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    task = _task(seeded, "발표 대본 작성")
    seoyeon = _user(seeded, "서연")
    login("지수")

    body = client.post(
        _url(room, f"/{task.id}/reassign"), json={"assignee_user_id": seoyeon.id}
    ).json()

    assert body["assignee_name"] == "서연"
    assert body["can_change_status"] is False  # 이제 지수 것이 아니다


def test_필요_없음으로_빼면_목록에서_빠지고_행은_남는다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    task = _task(seeded, "대면 회의 장소 예약")
    login("민지")

    res = client.post(_url(room, f"/{task.id}/dismiss"))

    assert res.status_code == 204
    titles = [t["title"] for t in client.get(_url(room)).json()["tasks"]]
    assert "대면 회의 장소 예약" not in titles
    seeded.refresh(task)
    assert task.dropped is True
    assert client.post(_url(room, f"/{task.id}/dismiss")).status_code == 404


def test_직접_추가하면_바로_확정된_할_일이_된다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    hyunwoo = _user(seeded, "현우")
    login("서연")

    res = client.post(
        _url(room),
        json={"title": "시연 리허설 장비 확인", "assignee_user_id": hyunwoo.id},
    )

    assert res.status_code == 201, res.text
    body = res.json()
    assert body["source"] is None
    assert body["state"] == "todo"
    created = seeded.get(Task, body["id"])
    assert created.origin == "manual"
    assert created.confirmed is True
    assert created.confirmed_by == _user(seeded, "서연").id
    titles = [t["title"] for t in client.get(_url(room)).json()["tasks"]]
    assert "시연 리허설 장비 확인" in titles


def test_회의록에서_추가하면_그_회의가_출처다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    meeting_id = _task(seeded, "사용자 인터뷰 정리").meeting_id
    login("서연")

    res = client.post(_url(room), json={"title": "회의 후속 메일", "meeting_id": meeting_id})

    assert res.status_code == 201, res.text
    body = res.json()
    assert body["source"]["meeting_id"] == meeting_id
    assert body["source"]["topic"] == "중간 발표 자료 나누기"
    assert seeded.get(Task, body["id"]).origin == "manual"
    detail = client.get(f"{API}/rooms/{room.id}/meetings/{meeting_id}").json()
    assert "회의 후속 메일" in [t["title"] for t in detail["tasks"]]


def test_없는_회의를_출처로_주면_404이고_안_만든다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    login("서연")
    before = len(seeded.exec(select(Task)).all())

    res = client.post(_url(room), json={"title": "엉뚱한 출처", "meeting_id": 999999})

    assert res.status_code == 404
    assert res.json()["code"] == "NOT_FOUND"
    seeded.expire_all()
    assert len(seeded.exec(select(Task)).all()) == before


def test_완료를_되돌리면_회의에서_끝난_일에서_빠진다(
    client: TestClient, seeded: Session, room: Room, login
) -> None:
    task = _task(seeded, "참고 사례 조사")
    meeting_id = task.done_meeting_id
    assert meeting_id is not None
    login("지수")  # 담당자
    meeting_url = f"{API}/rooms/{room.id}/meetings/{meeting_id}"
    assert [t["title"] for t in client.get(meeting_url).json()["done_tasks"]] == ["참고 사례 조사"]

    res = client.patch(_url(room, f"/{task.id}/status"), json={"state": "doing"})
    assert res.status_code == 200, res.text
    assert client.get(meeting_url).json()["done_tasks"] == []

    # 다시 완료로 바꿔도 "회의에서 끝난 일"로 돌아오지 않는다(회의 밖에서 끝냈으므로)
    client.patch(_url(room, f"/{task.id}/status"), json={"state": "done"})
    assert client.get(meeting_url).json()["done_tasks"] == []
