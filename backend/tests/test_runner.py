"""조율을 뒷단에서 돌리는 것과, 스트림이 그걸 따라 읽는 것.

**왜 이 파일이 있나.** 전에는 라운드가 `GET /stream` 응답 안에서 돌았다.
그래서 두 번째로 연 사람은 그때까지 쌓인 것만 보고 끝났고, 탭을 닫으면
조율이 멈춰 그 방이 영영 새 조율을 못 열었다. 둘 다 테스트가 없어서
몰랐다 — 기존 테스트는 **첫 스트림이 끝난 뒤에** 두 번째를 열어서
"도는 중에 열면"이 한 번도 안 돌았다.

conftest의 session 픽스처가 runner.start를 같은 자리에서 돌게 바꾼다.
스레드를 진짜로 띄우는 것은 맨 아래 한 건에서만 본다.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.main import app
from app.me.models import Preference
from app.meeting import router as runner_router
from app.meeting import runner
from app.meeting.models import Scheduling, Utterance
from app.shared.base import KST
from app.shared.db import session_dep
from app.shared.enums import Mode, SchedulingStatus, SpeakerKind
from app.shared.models import Membership, Room, User

API = "/api/v1"

MON = datetime(2026, 11, 9, 0, 0, tzinfo=KST)
WINDOW_START = MON + timedelta(hours=9)
WINDOW_END = MON + timedelta(days=4, hours=18)


@pytest.fixture(autouse=True)
def 빠르게(monkeypatch: pytest.MonkeyPatch) -> None:
    """발언 간격을 없앤다. 1.6초씩 기다리면 테스트가 분 단위가 된다."""
    monkeypatch.setattr("app.meeting.router.STEP_SEC", 0)


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[session_dep] = lambda: session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def 방(session: Session) -> Room:
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
            Membership(room_id=room.id, user_id=현우.id, part="개발"),
            Preference(user_id=지수.id, day_start_min=9 * 60, day_end_min=22 * 60),
            Preference(user_id=현우.id, day_start_min=9 * 60, day_end_min=22 * 60),
        ]
    )
    session.commit()
    return room


def _start(client: TestClient, room_id: int) -> dict:
    assert client.post(f"{API}/sessions", json={"name": "지수"}).status_code == 201
    res = client.post(
        f"{API}/rooms/{room_id}/schedulings",
        json={
            "topic": "중간 발표 준비",
            "window_start": WINDOW_START.isoformat(),
            "window_end": WINDOW_END.isoformat(),
            "duration_min": 60,
            "mode": Mode.ANY.value,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _발언들(본문: str) -> list[dict]:
    return [json.loads(l[6:]) for l in 본문.splitlines() if l.startswith("data: ")]


# ── 뒷단에서 돈다 ────────────────────────────────────────────────────


def test_스트림을_안_열어도_조율이_끝까지_간다(
    client: TestClient, session: Session, 방: Room
) -> None:
    """이게 핵심이다. 전에는 아무도 안 보면 라운드가 한 번도 안 돌았다."""
    started = _start(client, 방.id)

    scheduling = session.get(Scheduling, started["id"])
    assert scheduling is not None
    session.refresh(scheduling)
    assert scheduling.status != SchedulingStatus.RUNNING
    assert session.exec(select(Utterance)).all()


def test_돌다_터져도_running으로_안_남는다(
    client: TestClient, session: Session, 방: Room, monkeypatch: pytest.MonkeyPatch
) -> None:
    """running으로 남으면 부분 유니크 인덱스 때문에 그 방이 영영 막힌다.

    DB를 비우는 것 말고는 푸는 길이 없어서, 시연 중이면 거기서 끝난다.
    """

    def 터진다(*args: object, **kw: object) -> None:
        raise RuntimeError("라운드가 터졌다")

    monkeypatch.setattr("app.meeting.runner.run_rounds", 터진다)
    started = _start(client, 방.id)

    scheduling = session.get(Scheduling, started["id"])
    assert scheduling is not None
    session.refresh(scheduling)
    assert scheduling.status == SchedulingStatus.FAILED


def test_터진_뒤에도_새_조율을_열_수_있다(
    client: TestClient, 방: Room, monkeypatch: pytest.MonkeyPatch
) -> None:
    """첫 조율이 터져도 두 번째가 409 ALREADY_RUNNING에 안 막혀야 한다."""
    진짜 = runner.run_rounds
    남은횟수 = {"터질것": 1}

    def 한번만_터진다(db: Session, scheduling: Scheduling):
        if 남은횟수["터질것"]:
            남은횟수["터질것"] -= 1
            raise RuntimeError("라운드가 터졌다")
        return 진짜(db, scheduling)

    monkeypatch.setattr("app.meeting.runner.run_rounds", 한번만_터진다)
    _start(client, 방.id)
    _start(client, 방.id)  # 409가 아니라 201이어야 한다


# ── 스트림은 읽기만 한다 ─────────────────────────────────────────────


def test_도는_중에_열어도_처음부터_끝까지_본다(
    client: TestClient, session: Session, 방: Room, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**전에 깨지던 자리다.**

    라운드를 반쯤 돌려 둔 상태(utterance 몇 개 + status는 running)를 만들고
    연다. 전에는 rounds_used가 이미 1이라 "재생" 갈래로 떨어져, 쌓인 것만
    보여 주고 바로 done을 보냈다 — 지수 화면에서는 아직 도는 중인데도.

    지금은 읽기만 하므로, 뒤에 생긴 발언까지 이어서 받아야 한다.
    """
    started = _start(client, 방.id)
    끝난것 = session.exec(select(Utterance).order_by(Utterance.seq)).all()  # type: ignore[arg-type]
    assert len(끝난것) >= 3, "라운드가 돌아야 이 테스트가 뜻이 있다"

    # 도는 중인 상태로 되돌린다: 발언 둘만 남기고 status는 running.
    scheduling = session.get(Scheduling, started["id"])
    assert scheduling is not None
    끝상태 = scheduling.status
    for u in 끝난것[2:]:
        session.delete(u)
    scheduling.status = SchedulingStatus.RUNNING
    session.add(scheduling)
    session.commit()

    # 스트림이 쌓인 둘을 보낸 뒤 상태를 물을 때, 그 사이에 나머지가 생긴
    # 것처럼 만든다 — 돌리는 쪽이 하는 일이다.
    남은것 = [
        {
            "round_no": u.round_no,
            "seq": u.seq,
            "speaker_kind": u.speaker_kind,
            "speaker_user_id": u.speaker_user_id,
            "text": u.text,
        }
        for u in 끝난것[2:]
    ]
    진짜상태 = runner_router._status
    호출 = {"n": 0}

    def 중간에_더_생긴다(db: Session, scheduling_id: int):
        """스트림이 상태를 **두 번째로** 물을 때, 그 사이에 조율이 끝났다.

        이 자리가 경주 상태다: 상태가 끝으로 바뀐 순간에 발언도 이미 다 있다.
        스트림이 상태를 먼저 읽고 발언을 읽어야 이걸 안 놓친다. 반대로
        읽으면 마지막 발언 셋을 버리고 닫는다.
        """
        호출["n"] += 1
        if 호출["n"] == 2:
            for row in 남은것:
                db.add(Utterance(scheduling_id=scheduling_id, **row))
            s = db.get(Scheduling, scheduling_id)
            assert s is not None
            s.status = 끝상태
            db.add(s)
            db.commit()
        return 진짜상태(db, scheduling_id)

    monkeypatch.setattr("app.meeting.router._status", 중간에_더_생긴다)

    with client.stream(
        "GET", f"{API}/rooms/{방.id}/schedulings/{started['id']}/stream"
    ) as res:
        본문 = "".join(res.iter_text())

    발언 = _발언들(본문)
    assert len(발언) == len(끝난것) + 1, "쌓인 것 + 뒤에 생긴 것 + done"
    assert [u["seq"] for u in 발언[:-1]] == [u.seq for u in 끝난것]
    assert "event: done" in 본문
    assert 발언[-1]["status"] == str(끝상태)


def test_돌리는_쪽이_죽으면_붙잡지_않고_닫는다(
    client: TestClient, session: Session, 방: Room, monkeypatch: pytest.MonkeyPatch
) -> None:
    """서버 프로세스가 통째로 죽은 경우의 바닥값. 영원히 매달리지 않는다."""
    started = _start(client, 방.id)
    scheduling = session.get(Scheduling, started["id"])
    assert scheduling is not None
    scheduling.status = SchedulingStatus.RUNNING  # 돌리던 쪽이 상태도 못 남겼다
    session.add(scheduling)
    session.commit()

    monkeypatch.setattr("app.meeting.router.STALL_SEC", -1)  # 바로 멈춘 것으로 본다
    with client.stream(
        "GET", f"{API}/rooms/{방.id}/schedulings/{started['id']}/stream"
    ) as res:
        본문 = "".join(res.iter_text())

    assert "event: done" in 본문
    assert _발언들(본문)[-1]["status"] == "running"


def test_여러_명이_같이_열어도_발언이_안_늘어난다(
    client: TestClient, session: Session, 방: Room
) -> None:
    """읽기만 하므로 몇 번을 열든 DB가 그대로여야 한다."""
    started = _start(client, 방.id)
    길 = f"{API}/rooms/{방.id}/schedulings/{started['id']}/stream"

    처음 = 0
    for _ in range(3):
        with client.stream("GET", 길) as res:
            발언 = _발언들("".join(res.iter_text()))
        처음 = 처음 or len(발언)
        assert len(발언) == 처음
    assert len(session.exec(select(Utterance)).all()) == 처음 - 1  # done 한 줄 빼고


# ── 진짜 스레드 ──────────────────────────────────────────────────────


def test_start는_스레드를_띄우고_바로_돌아온다(monkeypatch: pytest.MonkeyPatch) -> None:
    """conftest가 평소엔 같은 자리에서 돌리므로, 스레드 자체는 여기서만 본다.

    DB를 안 탄다 — run_to_end를 바꿔치기해 "다른 스레드에서 불렸는가"만 본다.
    """
    import threading

    불린곳: list[str] = []
    끝남 = threading.Event()

    def 기록(scheduling_id: int) -> None:
        불린곳.append(threading.current_thread().name)
        끝남.set()

    monkeypatch.setattr("app.meeting.runner.run_to_end", 기록)
    runner.start(42)

    assert 끝남.wait(timeout=5), "스레드가 안 돌았습니다"
    assert 불린곳 == ["scheduling-42"]
    assert 불린곳[0] != threading.current_thread().name


def test_없는_조율이면_조용히_끝난다(session: Session) -> None:
    """지워진 조율을 돌리라고 해도 터지지 않는다."""
    runner.run_to_end(9999)


def test_발언_순서가_seq대로_나간다(
    client: TestClient, session: Session, 방: Room
) -> None:
    """화면이 받은 순서대로 쌓으므로 뒤섞이면 대화가 안 읽힌다."""
    started = _start(client, 방.id)
    with client.stream(
        "GET", f"{API}/rooms/{방.id}/schedulings/{started['id']}/stream"
    ) as res:
        발언 = _발언들("".join(res.iter_text()))[:-1]

    seqs = [u["seq"] for u in 발언]
    assert seqs == sorted(seqs) == list(range(1, len(seqs) + 1))
    assert 발언[0]["speaker_kind"] in (SpeakerKind.MEMBER, SpeakerKind.JUDGE)
