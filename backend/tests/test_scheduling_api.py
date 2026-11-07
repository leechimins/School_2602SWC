"""조율 시작과 조회. 실제 요청으로 본다.

여기까지가 LLM 없이 도는 전부다 — scheduling 한 행, 후보, 사람별 불편 점수.
라운드를 도는 것은 공급자를 고른 뒤다.
"""

from __future__ import annotations

import json
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
from app.meeting.models import CandidateSlot, Meeting, Scheduling, SlotCost, Utterance
from app.shared import demo_clock
from app.shared.base import KST
from app.shared.db import session_dep
from app.shared.enums import (
    MeetingStatus,
    Mode,
    Recurrence,
    ScheduleKind,
    ScheduleSource,
    SchedulingPhase,
)
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


@pytest.fixture
def 열기만(monkeypatch: pytest.MonkeyPatch) -> None:
    """조율을 **열기만** 하고 라운드는 안 돌린다.

    운영에서는 POST가 뒷단 스레드를 띄우고 바로 돌아오므로, 응답 시점의
    조율은 running이고 발언이 0개다. 테스트는 같은 자리에서 라운드를 돌려
    (conftest) 이 모양이 안 나온다. 열기 자체를 보는 테스트가 이걸 쓴다.
    """
    monkeypatch.setattr("app.meeting.runner.start", lambda scheduling_id: None)


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


def test_조율을_열면_후보가_생긴다(client: TestClient, 방: 팀, 열기만: None) -> None:
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
    client: TestClient, session: Session, 방: 팀,
    열기만: None,
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

    # 한 사람만 안 되면 1명 불참안 재료로 남는다. 전부 absent 단계다.
    slots = session.exec(select(CandidateSlot)).all()
    assert slots
    assert all(s.absentee_user_id == 방.현우.id for s in slots)
    assert all(s.phase == SchedulingPhase.ABSENT for s in slots)

    # 조율 시작은 끝 상태를 정하지 않는다. 라운드 루프가 정한다 —
    # absent 단계에서 합의하면 no_common이 된다.
    assert res.json()["status"] == "running"  # type: ignore[attr-defined]
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
    # 쓸 수 있는 후보가 아예 없으면 라운드를 돌 것이 없다. 괜히 스트림을
    # 열게 하지 않고 바로 failed다.
    assert res.json()["status"] == "failed"  # type: ignore[attr-defined]
    assert res.json()["candidate_count"] == 0  # type: ignore[attr-defined]
    assert session.exec(select(CandidateSlot)).all() == []


def test_가능_시간이_안_겹치면_후보가_없다(
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
    assert res.json()["status"] == "failed"  # type: ignore[attr-defined]
    assert res.json()["candidate_count"] == 0  # type: ignore[attr-defined]


def test_한_방에_도는_조율은_하나뿐이다(client: TestClient, 방: 팀, 열기만: None) -> None:
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


# ── 발언 스트림 ──────────────────────────────────────────────────────


def test_스트림이_발언을_흘리고_끝을_알린다(
    client: TestClient, 방: 팀, monkeypatch: pytest.MonkeyPatch
) -> None:
    """11/5에 이 테스트가 없어서 두 번 터졌다 — utterance.phase를 지운 뒤
    라우터에 남은 참조, 그리고 status.value(DB에서 읽으면 str이라 없다).
    둘 다 pytest는 통과하는데 서버만 죽는 종류였다.
    """
    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.setattr("app.meeting.router.STEP_SEC", 0)
    _login(client, "지수")
    started = _start(client, 방.room.id).json()  # type: ignore[union-attr,attr-defined]

    with client.stream(
        "GET", f"{API}/rooms/{방.room.id}/schedulings/{started['id']}/stream"
    ) as res:
        assert res.status_code == 200
        본문 = "".join(res.iter_text())

    발언 = [json.loads(l[6:]) for l in 본문.splitlines() if l.startswith("data: ")]
    assert len(발언) >= 2
    assert "event: done" in 본문

    끝 = 발언[-1]
    assert 끝["status"] in ("agreed", "settled", "failed")

    # 이름이 채워져야 한다. 비면 화면에 "1: 지수는…"처럼 숫자가 나온다.
    팀원발언 = [u for u in 발언[:-1] if u["speaker_kind"] == "member"]
    assert 팀원발언
    assert all(u["speaker_name"] for u in 팀원발언)
    assert all(u["speaker_name"] in ("지수", "현우") for u in 팀원발언)


def test_두_번_열어도_루프는_한_번만_돈다(
    client: TestClient, session: Session, 방: 팀, monkeypatch: pytest.MonkeyPatch
) -> None:
    """두 사람이 같이 열면 발언이 두 줄기로 섞여 핵심 화면이 망가진다."""
    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.setattr("app.meeting.router.STEP_SEC", 0)
    _login(client, "지수")
    started = _start(client, 방.room.id).json()  # type: ignore[union-attr,attr-defined]
    길 = f"{API}/rooms/{방.room.id}/schedulings/{started['id']}/stream"

    with client.stream("GET", 길) as res:
        처음 = "".join(res.iter_text())
    쌓인것 = len(session.exec(select(Utterance)).all())

    with client.stream("GET", 길) as res:
        다시 = "".join(res.iter_text())

    # 재생이라 발언 수가 늘지 않는다.
    assert len(session.exec(select(Utterance)).all()) == 쌓인것
    assert 처음.count("data: ") == 다시.count("data: ")


def test_확정_대기_회의도_후보에서_빠진다(
    client: TestClient, session: Session, 방: 팀
) -> None:
    """전에는 confirmed만 뺐다.

    1차 조율이 합의되고 아직 아무도 수락을 안 눌렀을 때 팀장이 2차 조율을
    열면, 같은 시간이 다시 후보로 나와 둘 다 확정될 수 있었다.
    """
    막힌때 = WINDOW_START.replace(hour=10)
    session.add(
        Meeting(
            room_id=방.room.id,  # type: ignore[arg-type]
            topic="1차 회의",
            start_at=막힌때,
            end_at=막힌때 + timedelta(hours=1),
            mode=Mode.OFFLINE,
            status=MeetingStatus.PROPOSED,  # 수락 대기가 끝나지 않고 남은 회의
        )
    )
    # 회의가 끝난 뒤로 시계를 둔다. 안 끝난 수락 대기 회의가 있으면 조율 자체를
    # 못 여는데(아래 테스트), 그건 새 조율을 막는 규칙이고 여기서 보려는 건
    # "남아 있는 proposed가 후보 시간을 차지하는가"다.
    demo_clock.set_clock(session, 막힌때 + timedelta(hours=2))
    session.commit()

    _login(client, "지수")
    started = _start(client, 방.room.id).json()  # type: ignore[union-attr,attr-defined]

    후보들 = session.exec(
        select(CandidateSlot).where(CandidateSlot.scheduling_id == started["id"])
    ).all()
    assert 후보들, "후보가 아예 없으면 이 테스트가 뜻이 없다"
    assert all(c.start_at != 막힌때 for c in 후보들)


def test_합의되면_조율_응답에_회의_번호가_실린다(
    client: TestClient, session: Session, 방: 팀
) -> None:
    """화면이 "조율 결과 확인하기"로 그 회의에 가려면 번호가 있어야 한다.
    전에는 빠져 있어서 버튼이 아예 안 그려졌다."""
    _login(client, "지수")
    started = _start(client, 방.room.id).json()  # type: ignore[union-attr,attr-defined]

    body = client.get(f"{API}/rooms/{방.room.id}/schedulings/{started['id']}").json()

    회의 = session.exec(select(Meeting)).one()
    assert body["status"] in ("agreed", "settled")
    assert body["meeting_id"] == 회의.id


def test_도는_중이면_회의_번호가_없다(client: TestClient, 방: 팀, 열기만: None) -> None:
    _login(client, "지수")
    body = _start(client, 방.room.id).json()  # type: ignore[union-attr,attr-defined]
    assert body["status"] == "running"
    assert body["meeting_id"] is None


def test_수락을_기다리는_회의가_있으면_새_조율을_못_연다(
    client: TestClient, session: Session, 방: 팀, 열기만: None
) -> None:
    """거절로 옛 조율을 되살릴 때 "한 방에 running 하나"와 부딪치지 않게, 그리고
    같은 시간이 후보로 또 나오지 않게 막는다."""
    회의때 = WINDOW_START.replace(hour=14)
    session.add(
        Meeting(
            room_id=방.room.id,  # type: ignore[arg-type]
            topic="1차 회의",
            start_at=회의때,
            end_at=회의때 + timedelta(hours=1),
            mode=Mode.OFFLINE,
            status=MeetingStatus.PROPOSED,
        )
    )
    demo_clock.set_clock(session, WINDOW_START - timedelta(days=1))  # 아직 안 지났다
    session.commit()

    _login(client, "지수")
    res = _start(client, 방.room.id)  # type: ignore[union-attr]

    assert res.status_code == 409  # type: ignore[attr-defined]
    assert res.json()["code"] == "AWAITING_RESPONSE"  # type: ignore[attr-defined]
    assert session.exec(select(Scheduling)).all() == []  # 조율 행도 안 생겼다


def test_이미_지난_수락_대기_회의는_새_조율을_막지_않는다(
    client: TestClient, session: Session, 방: 팀, 열기만: None
) -> None:
    """아무도 안 답하고 시간이 지나 버린 회의가 영영 팀장을 막으면 안 된다."""
    회의때 = WINDOW_START.replace(hour=14)
    session.add(
        Meeting(
            room_id=방.room.id,  # type: ignore[arg-type]
            topic="1차 회의",
            start_at=회의때,
            end_at=회의때 + timedelta(hours=1),
            mode=Mode.OFFLINE,
            status=MeetingStatus.PROPOSED,
        )
    )
    demo_clock.set_clock(session, 회의때 + timedelta(days=1))  # 회의가 끝난 뒤
    session.commit()

    _login(client, "지수")
    assert _start(client, 방.room.id).status_code == 201  # type: ignore[union-attr,attr-defined]
