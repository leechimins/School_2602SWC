"""홈 한 화면. 네 곳에서 재료를 모아 한 번에 준다.

여기서 지켜야 하는 것이 둘이다.

**오늘이 서버에서 온다.** 디데이도 할 일 묶음도 "오늘"로 갈리는데, 둘이
다른 시계를 보면 시연에서 날짜를 옮겼을 때 디데이와 묶음이 어긋난다.

**다음 회의는 하나뿐이다.** 일정 탭은 전부를 보여 주지만 홈은 요약이다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.meeting.models import Meeting, MeetingResponse, Scheduling
from app.minutes.models import Task
from app.notice.models import Notification
from app.shared import demo_clock
from app.shared.base import KST
from app.shared.enums import (
    MeetingStatus,
    Mode,
    NotificationKind,
    ResponseState,
    SchedulingStatus,
    TaskOrigin,
    TaskState,
)
from app.shared.models import Membership, Room, User

API = "/api/v1"
오늘 = datetime(2026, 11, 10, 9, 0, tzinfo=KST)


class 팀:
    def __init__(self, room: Room, 지수: User, 현우: User) -> None:
        self.room, self.지수, self.현우 = room, 지수, 현우

    @property
    def rid(self) -> int:
        assert self.room.id is not None
        return self.room.id


@pytest.fixture
def 방(session: Session) -> 팀:
    지수, 현우 = User(name="지수"), User(name="현우")
    session.add_all([지수, 현우])
    session.flush()
    room = Room(
        name="서비스디자인 팀 프로젝트",
        start_date=date(2026, 10, 13),
        due_date=date(2026, 12, 11),
        eval_method="최종 발표 + 시연",
        member_count=4,  # 네 명 방인데 둘만 들어왔다
        invite_code="T9K2QM",
        leader_user_id=지수.id,  # type: ignore[arg-type]
    )
    session.add(room)
    session.flush()
    session.add_all(
        [
            Membership(room_id=room.id, user_id=지수.id),  # type: ignore[arg-type]
            Membership(room_id=room.id, user_id=현우.id),  # type: ignore[arg-type]
        ]
    )
    session.commit()
    demo_clock.set_clock(session, 오늘)
    return 팀(room, 지수, 현우)


def _할일(session: Session, 방: 팀, 제목: str, **kw: object) -> Task:
    base: dict[str, object] = {
        "room_id": 방.rid,
        "title": 제목,
        "assignee_user_id": 방.지수.id,
        "state": TaskState.TODO,
        "origin": TaskOrigin.MANUAL,
        "confirmed": True,
        # confirmed가 참이면 confirmed_at도 있어야 한다(ck_task_confirmed).
        "confirmed_at": 오늘,
    }
    base.update(kw)
    if not base["confirmed"]:
        base["confirmed_at"] = None
    task = Task(**base)  # type: ignore[arg-type]
    session.add(task)
    session.commit()
    return task


def _회의(session: Session, 방: 팀, 시작: datetime, **kw: object) -> Meeting:
    base: dict[str, object] = {
        "room_id": 방.rid,
        "topic": "중간 점검 전 회의",
        "start_at": 시작,
        "end_at": 시작 + timedelta(hours=2),
        "mode": Mode.ONLINE,
        "status": MeetingStatus.PROPOSED,
    }
    base.update(kw)
    meeting = Meeting(**base)  # type: ignore[arg-type]
    session.add(meeting)
    session.commit()
    return meeting


# ── 기간 카드 ───────────────────────────────────────────────────────


def test_디데이와_오늘이_서버에서_온다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """프론트가 자기 시계로 세면 시연에서 날짜를 옮겼을 때 어긋난다."""
    login("지수")
    body = client.get(f"{API}/rooms/{방.rid}/home").json()

    assert body["today"] == "2026-11-10"
    assert body["start_date"] == "2026-10-13"
    assert body["due_date"] == "2026-12-11"
    assert body["d_day"] == 31  # 11/10 → 12/11


def test_시연_시계를_옮기면_디데이가_따라온다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    demo_clock.set_clock(session, datetime(2026, 12, 11, 9, 0, tzinfo=KST))
    login("지수")
    body = client.get(f"{API}/rooms/{방.rid}/home").json()
    assert body["d_day"] == 0  # 오늘이 마감


# ── 권한과 초대 ─────────────────────────────────────────────────────


def test_회의_잡기_버튼은_팀장에게만(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """브리프: 새 회의 잡기 버튼은 홈에만 두고 팀장만."""
    login("지수")
    assert client.get(f"{API}/rooms/{방.rid}/home").json()["can_start_scheduling"]
    login("현우")
    assert not client.get(f"{API}/rooms/{방.rid}/home").json()["can_start_scheduling"]


def test_초대_코드와_들어온_인원을_준다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """방을 막 만든 직후 화면이 쓴다."""
    login("지수")
    body = client.get(f"{API}/rooms/{방.rid}/home").json()
    assert body["invite_code"] == "T9K2QM"
    assert (body["joined_count"], body["member_count"]) == (2, 4)


def test_방_사람이_아니면_못_본다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    session.add(User(name="연우"))
    session.commit()
    login("연우")
    assert client.get(f"{API}/rooms/{방.rid}/home").status_code == 403


def test_로그인_없이는_못_본다(client: TestClient, 방: 팀) -> None:
    assert client.get(f"{API}/rooms/{방.rid}/home").status_code == 401


# ── 다음 회의 ───────────────────────────────────────────────────────


def test_잡힌_회의가_없으면_비어_있다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    login("지수")
    body = client.get(f"{API}/rooms/{방.rid}/home").json()
    assert body["next_meeting"] is None
    assert body["coordinating"] is None


def test_다음_회의는_가장_이른_것_하나다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """일정 탭은 전부를 보여 주지만 홈은 하나만 요약한다."""
    _회의(session, 방, 오늘 + timedelta(days=8), topic="나중 것")
    이른것 = _회의(session, 방, 오늘 + timedelta(days=2), topic="이른 것")
    login("지수")

    body = client.get(f"{API}/rooms/{방.rid}/home").json()
    assert body["next_meeting"]["id"] == 이른것.id
    assert body["next_meeting"]["topic"] == "이른 것"


def test_지난_회의는_다음_회의가_아니다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    _회의(session, 방, 오늘 - timedelta(days=3))
    login("지수")
    assert client.get(f"{API}/rooms/{방.rid}/home").json()["next_meeting"] is None


def test_응답_상태를_같이_준다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """홈 카드가 "수락 2/4 · 내 응답 대기"를 그린다."""
    meeting = _회의(session, 방, 오늘 + timedelta(days=2))
    session.add_all(
        [
            MeetingResponse(
                meeting_id=meeting.id,  # type: ignore[arg-type]
                user_id=방.지수.id,  # type: ignore[arg-type]
                state=ResponseState.PENDING,
            ),
            MeetingResponse(
                meeting_id=meeting.id,  # type: ignore[arg-type]
                user_id=방.현우.id,  # type: ignore[arg-type]
                state=ResponseState.ACCEPTED,
                responded_at=오늘,
            ),
        ]
    )
    session.commit()
    login("지수")

    카드 = client.get(f"{API}/rooms/{방.rid}/home").json()["next_meeting"]
    assert (카드["accepted"],카드["responders"]) == (1, 2)
    assert 카드["my_state"] == "pending"
    assert 카드["status"] == "proposed"
    assert 카드["settled"] is False


def test_조정으로_정해진_회의는_표시가_붙는다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    s = Scheduling(
        room_id=방.rid,
        started_by=방.지수.id,  # type: ignore[arg-type]
        topic="중간 점검 전 회의",
        window_start=오늘,
        window_end=오늘 + timedelta(days=4),
        duration_min=120,
        mode=Mode.ONLINE,
        status=SchedulingStatus.SETTLED,
    )
    session.add(s)
    session.flush()
    _회의(
        session, 방, 오늘 + timedelta(days=2),
        scheduling_id=s.id, status=MeetingStatus.CONFIRMED,
    )
    login("지수")
    assert client.get(f"{API}/rooms/{방.rid}/home").json()["next_meeting"]["settled"]


def test_도는_조율이_있으면_보여_준다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """잡힌 회의가 없어도 "조율 중"이 자리를 잡는다."""
    session.add(
        Scheduling(
            room_id=방.rid,
            started_by=방.지수.id,  # type: ignore[arg-type]
            topic="발표 리허설",
            window_start=오늘,
            window_end=오늘 + timedelta(days=4),
            duration_min=120,
            mode=Mode.ANY,
            status=SchedulingStatus.RUNNING,
        )
    )
    session.commit()
    login("지수")

    body = client.get(f"{API}/rooms/{방.rid}/home").json()
    assert body["coordinating"]["topic"] == "발표 리허설"
    assert body["next_meeting"] is None


# ── 내 할 일 ────────────────────────────────────────────────────────


def test_할_일이_다섯_갈래로_묶인다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """브리프: 기한 지남 / 오늘 / 내일 / 그 이후 / 완료."""
    _할일(session, 방, "지난 것", due_date=date(2026, 11, 8))
    _할일(session, 방, "오늘 것", due_date=date(2026, 11, 10))
    _할일(session, 방, "내일 것", due_date=date(2026, 11, 11))
    _할일(session, 방, "나중 것", due_date=date(2026, 11, 20))
    _할일(session, 방, "기한 없는 것")
    _할일(session, 방, "끝난 것", due_date=date(2026, 11, 1), state=TaskState.DONE)
    login("지수")

    묶음 = {t["title"]: t["bucket"] for t in client.get(f"{API}/rooms/{방.rid}/home").json()["my_tasks"]}
    assert 묶음 == {
        "지난 것": "late", "오늘 것": "today", "내일 것": "tomorrow",
        "나중 것": "later", "기한 없는 것": "later", "끝난 것": "done",
    }


def test_끝난_일은_늦지_않는다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """기한이 지났어도 완료면 done이다. 끝난 일에 늦음 뱃지를 붙이면 안 된다."""
    _할일(session, 방, "끝난 것", due_date=date(2026, 11, 1), state=TaskState.DONE)
    login("지수")
    t = client.get(f"{API}/rooms/{방.rid}/home").json()["my_tasks"][0]
    assert t["bucket"] == "done"
    assert t["late"] is False


def test_기한_순으로_나온다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """브리프: 기한 순 하나로만. 날짜별·종류별 바꾸기는 없다."""
    _할일(session, 방, "셋", due_date=date(2026, 11, 20))
    _할일(session, 방, "하나", due_date=date(2026, 11, 8))
    _할일(session, 방, "둘", due_date=date(2026, 11, 11))
    login("지수")
    제목 = [t["title"] for t in client.get(f"{API}/rooms/{방.rid}/home").json()["my_tasks"]]
    assert 제목 == ["하나", "둘", "셋"]


def test_막힘_뱃지가_붙는다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    _할일(session, 방, "막힌 것", due_date=date(2026, 11, 20), state=TaskState.BLOCKED)
    login("지수")
    assert client.get(f"{API}/rooms/{방.rid}/home").json()["my_tasks"][0]["blocked"]


def test_남의_할_일과_확정_전_제안은_안_나온다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """홈은 "지금 내가 무엇을 봐야 하는지"다.

    확정 전 AI 제안은 회의록에서 팀이 함께 고르는 것이라 내 할 일이 아니다.
    """
    _할일(session, 방, "현우 것", assignee_user_id=방.현우.id)
    _할일(session, 방, "아직 제안", confirmed=False, origin=TaskOrigin.AI)
    _할일(session, 방, "내 것")
    login("지수")

    제목 = [t["title"] for t in client.get(f"{API}/rooms/{방.rid}/home").json()["my_tasks"]]
    assert 제목 == ["내 것"]


# ── 알림 ────────────────────────────────────────────────────────────


def test_안_읽은_알림만_센다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    for i, read in enumerate([None, None, 오늘]):
        session.add(
            Notification(
                room_id=방.rid,
                user_id=방.지수.id,  # type: ignore[arg-type]
                kind=NotificationKind.LATE,
                reason="기한이 지났습니다",
                dedupe_key=f"late:task{i}",
                read_at=read,
                created_at=오늘,
            )
        )
    session.add(
        Notification(
            room_id=방.rid,
            user_id=방.현우.id,  # type: ignore[arg-type]
            kind=NotificationKind.LATE,
            reason="기한이 지났습니다",
            dedupe_key="late:other",
            created_at=오늘,
        )
    )
    session.commit()
    login("지수")

    assert client.get(f"{API}/rooms/{방.rid}/home").json()["unread_notifications"] == 2
