"""에이전트가 먼저 꺼내는 "회의 잡을까요?"(app/home/suggest.py). 홈 응답으로 본다.

방: 10/13 시작, 12/11 마감. 오늘 11/10(화) 9시. 회의는 아직 한 번도 없다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.meeting.models import Scheduling
from app.shared import demo_clock
from app.shared.base import KST
from app.shared.enums import MeetingStatus, Mode, SchedulingStatus, TaskState

from test_home_api import API, _할일, _회의, 방, 오늘, 팀  # noqa: F401


def _제안(client: TestClient, 방: 팀) -> dict | None:
    return client.get(f"{API}/rooms/{방.rid}/home").json()["suggestion"]


def test_한_번도_안_만났으면_첫_회의를_권한다(client: TestClient, 방: 팀, login) -> None:
    login("지수")
    s = _제안(client, 방)
    assert s is not None and s["kind"] == "gap" and s["topic"] == "첫 회의"
    assert "28일" in s["reason"]
    # 내일부터 5일
    assert (s["window_start"], s["window_end"]) == ("2026-11-11", "2026-11-15")


def test_팀원에게는_안_보인다(client: TestClient, 방: 팀, login) -> None:
    login("현우")
    assert _제안(client, 방) is None


def test_막힌_일이_가장_먼저다(client: TestClient, session: Session, 방: 팀, login) -> None:
    _할일(session, 방, "보고서 초안", due_date=date(2026, 11, 5))  # 늦음
    _할일(session, 방, "자료 조사", state=TaskState.BLOCKED, due_date=date(2026, 11, 20))
    _할일(session, 방, "설문 정리", state=TaskState.BLOCKED, due_date=date(2026, 11, 12))
    login("지수")
    s = _제안(client, 방)
    assert s is not None and s["kind"] == "blocked"
    # 기한이 빠른 막힌 일이 주제가 된다
    assert s["topic"] == "설문 정리 같이 풀기"
    assert "‘설문 정리’ 외 1개" in s["reason"]
    assert (s["window_start"], s["window_end"]) == ("2026-11-11", "2026-11-13")


def test_기한_지난_일을_센다(client: TestClient, session: Session, 방: 팀, login) -> None:
    _할일(session, 방, "보고서 초안", due_date=date(2026, 11, 5))
    _할일(session, 방, "발표 개요", due_date=date(2026, 11, 9))
    _할일(session, 방, "끝난 일", due_date=date(2026, 11, 1), state=TaskState.DONE)
    _할일(session, 방, "확정 전 제안", due_date=date(2026, 11, 1), confirmed=False)
    _할일(session, 방, "필요 없음", due_date=date(2026, 11, 1), dropped=True)
    login("지수")
    s = _제안(client, 방)
    assert s is not None and s["kind"] == "late"
    assert "2개" in s["reason"]


def test_마감이_2주_안이면_준비_회의를_권한다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    demo_clock.set_clock(session, datetime(2026, 12, 1, 9, 0, tzinfo=KST))
    login("지수")
    s = _제안(client, 방)
    assert s is not None and s["kind"] == "deadline"
    assert s["topic"] == "최종 발표 + 시연 준비" and "10일" in s["reason"]
    assert (s["window_start"], s["window_end"]) == ("2026-12-02", "2026-12-08")


def test_기간은_마감을_넘지_않는다(client: TestClient, session: Session, 방: 팀, login) -> None:
    demo_clock.set_clock(session, datetime(2026, 12, 8, 9, 0, tzinfo=KST))
    login("지수")
    s = _제안(client, 방)
    assert s is not None and (s["window_start"], s["window_end"]) == ("2026-12-09", "2026-12-11")


def test_마감_당일엔_조용하다(client: TestClient, session: Session, 방: 팀, login) -> None:
    demo_clock.set_clock(session, datetime(2026, 12, 11, 9, 0, tzinfo=KST))
    login("지수")
    assert _제안(client, 방) is None


def test_마감이_지나면_조용하다(client: TestClient, session: Session, 방: 팀, login) -> None:
    demo_clock.set_clock(session, datetime(2026, 12, 12, 9, 0, tzinfo=KST))
    login("지수")
    assert _제안(client, 방) is None


def test_일주일_안에_잡힌_회의가_있으면_조용하다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    _할일(session, 방, "자료 조사", state=TaskState.BLOCKED)
    _회의(session, 방, 오늘 + timedelta(days=3))  # 확정 대기
    login("지수")
    assert _제안(client, 방) is None


def test_잡힌_회의가_일주일보다_뒤면_제안한다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    _할일(session, 방, "자료 조사", state=TaskState.BLOCKED)
    _회의(session, 방, 오늘 + timedelta(days=9), status=MeetingStatus.CONFIRMED)
    login("지수")
    s = _제안(client, 방)
    assert s is not None and s["kind"] == "blocked"


def test_조율이_도는_중이면_조용하다(client: TestClient, session: Session, 방: 팀, login) -> None:
    session.add(Scheduling(
        room_id=방.rid, started_by=방.지수.id, topic="중간 발표",  # type: ignore[arg-type]
        window_start=오늘, window_end=오늘 + timedelta(days=4), duration_min=60,
        mode=Mode.ANY, status=SchedulingStatus.RUNNING,
    ))
    session.commit()
    login("지수")
    assert _제안(client, 방) is None


def test_최근에_만났으면_간격_제안은_없다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    _회의(session, 방, 오늘 - timedelta(days=3), status=MeetingStatus.DONE)
    login("지수")
    assert _제안(client, 방) is None


def test_지난_회의_후_일주일이_넘으면_정기_회의를_권한다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    _회의(session, 방, 오늘 - timedelta(days=9), status=MeetingStatus.DONE)
    _회의(session, 방, 오늘 - timedelta(days=5), status=MeetingStatus.CANCELLED)  # 취소는 안 센다
    login("지수")
    s = _제안(client, 방)
    assert s is not None and s["kind"] == "gap" and s["topic"] == "정기 회의"
    assert "9일" in s["reason"]
