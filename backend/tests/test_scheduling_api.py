"""조율 시작과 조회. 실제 요청으로 본다.

여기까지가 LLM 없이 도는 전부다 — scheduling 한 행, 후보, 사람별 불편 점수.
라운드를 도는 것은 공급자를 고른 뒤다.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.main import app
from app.me.models import Preference, ScheduleItem
from app.meeting import scorer
from app.meeting.models import CandidateSlot, SlotCost
from app.shared.base import KST
from app.shared.db import session_dep
from app.shared.enums import Mode, Recurrence, ScheduleKind, ScheduleSource
from app.shared.models import Membership, Room, User

API = "/api/v1"

# 2026-11-09는 월요일. 기간은 월~금 한 주다.
MON = datetime(2026, 11, 9, 0, 0, tzinfo=KST)
WINDOW_START = MON + timedelta(hours=9)
WINDOW_END = MON + timedelta(days=4, hours=18)


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[session_dep] = lambda: session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class 팀:
    def __init__(self, room: Room, 지수: User, 현우: User) -> None:
        self.room = room
        self.지수 = 지수  # 팀장
        self.현우 = 현우


@pytest.fixture
def 방(session: Session) -> 팀:
    """팀장 지수 + 팀원 현우. 둘 다 9시~22시 가능하다고 답한 상태."""
    지수 = User(name="지수")
    현우 = User(name="현우")
    session.add_all([지수, 현우])
    session.flush()
    assert 지수.id is not None and 현우.id is not None

    room = Room(
        name="서비스디자인 팀 프로젝트",
        start_date=date(2026, 10, 20),
        due_date=date(2026, 12, 11),
        eval_method="최종 발표 + 시연",
        member_count=2,
        invite_code="T9K2QM",
        leader_user_id=지수.id,
    )
    session.add(room)
    session.flush()
    assert room.id is not None

    session.add_all(
        [
            Membership(room_id=room.id, user_id=지수.id, part="자료조사"),
            Membership(room_id=room.id, user_id=현우.id, part="개발", yield_total=3),
            Preference(user_id=지수.id, day_start_min=9 * 60, day_end_min=22 * 60),
            Preference(user_id=현우.id, day_start_min=9 * 60, day_end_min=22 * 60),
        ]
    )
    session.commit()
    return 팀(room, 지수, 현우)


def _login(client: TestClient, name: str) -> None:
    assert client.post(f"{API}/sessions", json={"name": name}).status_code == 201


def _start(client: TestClient, room_id: int, **kw) -> object:
    body = {
        "topic": "중간 발표 준비",
        "window_start": WINDOW_START.isoformat(),
        "window_end": WINDOW_END.isoformat(),
        "duration_min": 60,
        "mode": Mode.ANY.value,
    }
    body.update(kw)
    return client.post(f"{API}/rooms/{room_id}/schedulings", json=body)


# ── 권한 ────────────────────────────────────────────────────────────


def test_팀장만_조율을_시작한다(client: TestClient, 방: 팀) -> None:
    """브리프: 방 생성하기와 조율 시작은 팀장만 합니다."""
    _login(client, "현우")
    res = _start(client, 방.room.id)  # type: ignore[union-attr]
    assert res.status_code == 403  # type: ignore[attr-defined]
    assert res.json()["code"] == "FORBIDDEN"  # type: ignore[attr-defined]


def test_로그인_없이는_못_시작한다(client: TestClient, 방: 팀) -> None:
    res = _start(client, 방.room.id)  # type: ignore[union-attr]
    assert res.status_code == 401  # type: ignore[attr-defined]


def test_없는_방이면_404다(client: TestClient, 방: 팀) -> None:
    _login(client, "지수")
    assert _start(client, 99999).status_code == 404  # type: ignore[attr-defined]


# ── 조율 시작 ────────────────────────────────────────────────────────


def test_조율을_열면_후보가_생긴다(client: TestClient, 방: 팀) -> None:
    _login(client, "지수")
    res = _start(client, 방.room.id)  # type: ignore[union-attr]
    assert res.status_code == 201, res.text  # type: ignore[attr-defined]

    body = res.json()  # type: ignore[attr-defined]
    assert body["status"] == "running"
    assert body["rounds_used"] == 0  # 라운드는 에이전트가 말할 때 올라간다
    assert body["candidate_count"] > 0
    assert body["utterances"] == []  # LLM이 아직 없다


def test_후보마다_사람_수만큼_점수가_생긴다(
    client: TestClient, session: Session, 방: 팀
) -> None:
    _login(client, "지수")
    _start(client, 방.room.id)  # type: ignore[union-attr]

    slots = session.exec(select(CandidateSlot)).all()
    assert slots
    for slot in slots:
        costs = session.exec(
            select(SlotCost).where(SlotCost.candidate_slot_id == slot.id)
        ).all()
        assert len(costs) == 2  # 지수 + 현우
        assert all(1 <= c.score <= 5 for c in costs)
        assert all(c.reason for c in costs)  # 에이전트가 말할 이유가 비면 안 된다


def test_후보는_다섯_개까지만_저장한다(
    client: TestClient, session: Session, 방: 팀
) -> None:
    """한 주 기간이면 채점기가 수십 개를 만든다. round_no의 뜻을 지킨다."""
    _login(client, "지수")
    _start(client, 방.room.id)  # type: ignore[union-attr]

    slots = session.exec(select(CandidateSlot)).all()
    assert len(slots) <= 5
    assert all(s.round_no == 1 for s in slots)
    assert all(s.proposed is False for s in slots)  # 아직 제안 안 했다


def test_겹치는_수업이_있으면_그_사람은_안_된다(
    client: TestClient, session: Session, 방: 팀
) -> None:
    """현우가 월~금 9시부터 22시까지 전부 알바면 어떤 후보에서도 안 된다."""
    for weekday in range(5):
        session.add(
            ScheduleItem(
                user_id=방.현우.id,  # type: ignore[arg-type]
                source=ScheduleSource.MANUAL,
                kind=ScheduleKind.PARTTIME,
                title="알바",
                recurrence=Recurrence.WEEKLY,
                weekday=weekday,
                start_min=9 * 60,
                end_min=22 * 60,
            )
        )
    session.commit()

    _login(client, "지수")
    res = _start(client, 방.room.id)  # type: ignore[union-attr]
    assert res.status_code == 201, res.text  # type: ignore[attr-defined]

    현우_점수 = session.exec(
        select(SlotCost).where(SlotCost.user_id == 방.현우.id)
    ).all()
    assert 현우_점수
    assert all(c.available is False for c in 현우_점수)
    assert all("알바와 겹칩니다" in c.reason for c in 현우_점수)

    # 한 사람만 안 되면 1명 불참안 재료로 남는다.
    slots = session.exec(select(CandidateSlot)).all()
    assert slots
    assert all(s.absentee_user_id == 방.현우.id for s in slots)

    # 전원 가능한 후보가 하나도 없으므로 no_common이다. 후보가 아예 없을
    # 때만이 아니다 — 화면이 1명 불참안으로 가야 한다.
    assert res.json()["status"] == "no_common"  # type: ignore[attr-defined]
    assert res.json()["candidate_count"] > 0  # type: ignore[attr-defined]


def test_두_명_이상_못_오는_후보는_저장하지_않는다(
    client: TestClient, session: Session, 방: 팀
) -> None:
    """브리프에 1명 불참안만 있다. 두 명을 빼는 회의는 제안할 수 없으므로,
    저장하면 라운드가 쓸 수 없는 행만 쌓인다.
    """
    for user_id in (방.지수.id, 방.현우.id):
        for weekday in range(5):
            session.add(
                ScheduleItem(
                    user_id=user_id,  # type: ignore[arg-type]
                    source=ScheduleSource.MANUAL,
                    kind=ScheduleKind.PARTTIME,
                    title="알바",
                    recurrence=Recurrence.WEEKLY,
                    weekday=weekday,
                    start_min=9 * 60,
                    end_min=22 * 60,
                )
            )
    session.commit()

    _login(client, "지수")
    res = _start(client, 방.room.id)  # type: ignore[union-attr]
    assert res.status_code == 201, res.text  # type: ignore[attr-defined]
    assert res.json()["status"] == "no_common"  # type: ignore[attr-defined]
    assert res.json()["candidate_count"] == 0  # type: ignore[attr-defined]
    assert session.exec(select(CandidateSlot)).all() == []


def test_가능_시간이_안_겹치면_no_common이다(
    client: TestClient, session: Session, 방: 팀
) -> None:
    """지수는 오전만, 현우는 밤만 가능하면 후보가 하나도 없다.

    서버가 몰래 기간을 넓히지 않는다 — 넓히는 것은 팀장의 선택이고,
    몰래 하면 "왜 이 시간이죠"에 답할 수 없다.
    """
    지수_선호 = session.exec(
        select(Preference).where(Preference.user_id == 방.지수.id)
    ).one()
    지수_선호.day_end_min = 11 * 60
    현우_선호 = session.exec(
        select(Preference).where(Preference.user_id == 방.현우.id)
    ).one()
    현우_선호.day_start_min = 21 * 60
    session.add_all([지수_선호, 현우_선호])
    session.commit()

    _login(client, "지수")
    res = _start(client, 방.room.id)  # type: ignore[union-attr]
    assert res.status_code == 201, res.text  # type: ignore[attr-defined]
    assert res.json()["status"] == "no_common"  # type: ignore[attr-defined]
    assert res.json()["candidate_count"] == 0  # type: ignore[attr-defined]


def test_한_방에_도는_조율은_하나뿐이다(client: TestClient, 방: 팀) -> None:
    """조율 중에 팀장이 한 번 더 누르면 발언이 두 줄기로 섞인다."""
    _login(client, "지수")
    assert _start(client, 방.room.id).status_code == 201  # type: ignore[union-attr,attr-defined]

    res = _start(client, 방.room.id)  # type: ignore[union-attr]
    assert res.status_code == 409  # type: ignore[attr-defined]
    assert res.json()["code"] == "ALREADY_RUNNING"  # type: ignore[attr-defined]


def test_다른_제약이_깨지면_409가_아니라_터진다(
    client: TestClient, 방: 팀, monkeypatch: pytest.MonkeyPatch
) -> None:
    """조율 시작은 다른 제약도 깨뜨릴 수 있다 — 채점 상수를 잘못 건드리면
    ck_slot_cost_score가, 라운드 루프를 붙일 때 ck_candidate_round가 걸린다.
    그건 우리 버그라서 "이미 진행 중입니다"로 덮으면 안 된다.

    에러 문장 속 글자를 찾는 방식이었다면 이 갈래가 조용히 뒤집혔다.
    """
    from app.meeting import service

    def 점수를_0으로(*args, **kw) -> list[scorer.Cost]:
        costs = 원래_채점(*args, **kw)
        return [replace(c, score=0) for c in costs]  # CHECK는 1~5만 받는다

    원래_채점 = service.score_slot
    monkeypatch.setattr(service, "score_slot", 점수를_0으로)

    _login(client, "지수")
    with pytest.raises(IntegrityError) as caught:
        _start(client, 방.room.id)  # type: ignore[union-attr]
    assert caught.value.orig.diag.constraint_name == "ck_slot_cost_score"


@pytest.mark.parametrize("duration", [45, 0, -30])
def test_회의_길이는_30분_단위다(client: TestClient, 방: 팀, duration: int) -> None:
    _login(client, "지수")
    res = _start(client, 방.room.id, duration_min=duration)  # type: ignore[union-attr]
    assert res.status_code == 400  # type: ignore[attr-defined]
    assert res.json()["code"] == "INVALID_INPUT"  # type: ignore[attr-defined]


@pytest.mark.parametrize("field", ["window_start", "window_end"])
def test_오프셋_없는_시각은_거절한다(client: TestClient, 방: 팀, field: str) -> None:
    """받아 주면 조용히 틀린다. naive에 astimezone(KST)를 부르면 서버의
    시간대로 해석하므로, 배포 서버가 UTC면 오전 9시가 오후 6시가 된다.
    """
    _login(client, "지수")
    naive = {field: WINDOW_START.replace(tzinfo=None).isoformat()}
    if field == "window_end":
        naive[field] = WINDOW_END.replace(tzinfo=None).isoformat()

    res = _start(client, 방.room.id, **naive)  # type: ignore[union-attr]
    assert res.status_code == 400  # type: ignore[attr-defined]
    assert res.json()["code"] == "INVALID_INPUT"  # type: ignore[attr-defined]
    assert res.json()["field"] == field  # type: ignore[attr-defined]


def test_기간이_거꾸로면_400이다(client: TestClient, 방: 팀) -> None:
    _login(client, "지수")
    res = _start(
        client,
        방.room.id,  # type: ignore[union-attr]
        window_start=WINDOW_END.isoformat(),
        window_end=WINDOW_START.isoformat(),
    )
    assert res.status_code == 400  # type: ignore[attr-defined]
    assert res.json()["field"] == "window_start"  # type: ignore[attr-defined]


def test_남의_점수는_응답에_안_담긴다(client: TestClient, 방: 팀) -> None:
    """명세 권장 규칙 3. 팀 전체 불편 합도 내부 숫자라 나가지 않는다."""
    _login(client, "지수")
    res = _start(client, 방.room.id)  # type: ignore[union-attr]
    text = res.text  # type: ignore[attr-defined]
    assert "total_cost" not in text
    assert "score" not in text


# ── 조율 조회 ────────────────────────────────────────────────────────


def test_재진입하면_같은_조율이_나온다(client: TestClient, 방: 팀) -> None:
    _login(client, "지수")
    started = _start(client, 방.room.id).json()  # type: ignore[union-attr,attr-defined]

    res = client.get(f"{API}/rooms/{방.room.id}/schedulings/{started['id']}")
    assert res.status_code == 200, res.text
    assert res.json()["topic"] == "중간 발표 준비"
    assert res.json()["candidate_count"] == started["candidate_count"]


def test_팀원도_조율을_읽을_수_있다(client: TestClient, 방: 팀) -> None:
    """나머지 팀원은 알림으로 바로 이 화면에 들어온다."""
    _login(client, "지수")
    started = _start(client, 방.room.id).json()  # type: ignore[union-attr,attr-defined]

    client.delete(f"{API}/sessions")
    _login(client, "현우")
    res = client.get(f"{API}/rooms/{방.room.id}/schedulings/{started['id']}")
    assert res.status_code == 200


def test_팀원이_아니면_못_읽는다(
    client: TestClient, session: Session, 방: 팀
) -> None:
    남 = User(name="남의팀사람")
    session.add(남)
    session.commit()

    _login(client, "지수")
    started = _start(client, 방.room.id).json()  # type: ignore[union-attr,attr-defined]

    client.delete(f"{API}/sessions")
    _login(client, "남의팀사람")
    res = client.get(f"{API}/rooms/{방.room.id}/schedulings/{started['id']}")
    assert res.status_code == 403
    assert res.json()["code"] == "FORBIDDEN"


def test_다른_방의_조율_id면_404다(
    client: TestClient, session: Session, 방: 팀
) -> None:
    """id만 바꿔 넣어 남의 방 조율을 들여다보는 것을 막는다."""
    _login(client, "지수")
    started = _start(client, 방.room.id).json()  # type: ignore[union-attr,attr-defined]

    다른방 = Room(
        name="다른 과제",
        start_date=date(2026, 10, 1),
        due_date=date(2026, 12, 1),
        eval_method="보고서",
        member_count=1,
        invite_code="ZZZZZZ",
        leader_user_id=방.지수.id,  # type: ignore[arg-type]
    )
    session.add(다른방)
    session.flush()
    session.add(Membership(room_id=다른방.id, user_id=방.지수.id))  # type: ignore[arg-type]
    session.commit()

    res = client.get(f"{API}/rooms/{다른방.id}/schedulings/{started['id']}")
    assert res.status_code == 404
