"""맡겨 두면 에이전트가 조율을 스스로 연다(app/home/auto.py). 홈을 열 때 돈다.

방과 시계는 test_home_suggest와 같다: 오늘 11/10, 회의 한 번도 없음 → "첫 회의" 제안.
라운드는 돌리지 않는다. 여기서 보는 것은 "언제 여나"뿐이다.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.meeting.models import Scheduling
from app.notice.models import AgentLog
from app.shared.enums import SchedulingStatus

from test_home_api import API, _회의, 방, 오늘, 팀  # noqa: F401


@pytest.fixture(autouse=True)
def 라운드는_안_돈다(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    # session 픽스처가 runner.start를 바꿔 끼운 뒤에 덮어써야 한다
    monkeypatch.setattr("app.meeting.runner.start", lambda scheduling_id: None)


def _맡기기(client: TestClient, 방: 팀, on: bool = True) -> int:
    return client.put(f"{API}/rooms/{방.rid}/agent-setting", json={"auto_schedule": on}).status_code


def _홈(client: TestClient, 방: 팀) -> dict:
    return client.get(f"{API}/rooms/{방.rid}/home").json()


def _조율들(session: Session, 방: 팀) -> list[Scheduling]:
    session.expire_all()
    return list(session.exec(select(Scheduling).where(Scheduling.room_id == 방.rid)).all())


def test_안_맡기면_제안만_한다(client: TestClient, session: Session, 방: 팀, login) -> None:
    login("지수")
    home = _홈(client, 방)
    assert home["auto_schedule"] is False and home["suggestion"] is not None
    assert _조율들(session, 방) == []


def test_팀원은_맡길_수_없다(client: TestClient, 방: 팀, login) -> None:
    login("현우")
    assert _맡기기(client, 방) == 403


def test_맡기면_팀원이_홈을_열_때_스스로_연다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    login("지수")
    assert _맡기기(client, 방) == 200
    login("현우")
    home = _홈(client, 방)

    [s] = _조율들(session, 방)
    assert s.topic == "첫 회의" and s.started_by == 방.지수.id
    assert s.window_start.astimezone().date() <= s.window_end.astimezone().date()
    assert home["auto_schedule"] is True
    # 이 방엔 선호가 없어 후보 없이 멈출 수도 있다. 그러면 "멈춤" 줄이 위에 하나 더 붙는다
    [line] = [l for l in home["agent_log"] if l["what"] == "첫 회의 조율을 스스로 시작"]
    assert "만난 적이 없어요" in line["why"]


def test_하루에_한_번만_연다(client: TestClient, session: Session, 방: 팀, login) -> None:
    login("지수")
    _맡기기(client, 방)
    _홈(client, 방)
    [s] = _조율들(session, 방)
    # 후보가 없어 끝난 것처럼 만든다. 같은 날 다시 열면 또 실패할 뿐이다.
    s.status = SchedulingStatus.FAILED
    session.add(s)
    session.commit()
    _홈(client, 방)
    assert len(_조율들(session, 방)) == 1


def test_수락_기다리는_회의가_있으면_안_연다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    _회의(session, 방, 오늘 + timedelta(days=9))  # 확정 대기, 7일 밖이라 제안은 뜬다
    login("지수")
    _맡기기(client, 방)
    _홈(client, 방)
    assert _조율들(session, 방) == []
    assert session.exec(select(AgentLog)).first() is None


def test_끄면_다시_제안만_한다(client: TestClient, session: Session, 방: 팀, login) -> None:
    login("지수")
    _맡기기(client, 방)
    _맡기기(client, 방, on=False)
    assert _홈(client, 방)["auto_schedule"] is False
    assert _조율들(session, 방) == []


def test_자동_조율이_터져도_홈은_뜬다(
    client: TestClient, session: Session, 방: 팀, login, monkeypatch: pytest.MonkeyPatch
) -> None:
    def 터짐(*args: object, **kwargs: object) -> None:
        raise RuntimeError("캘린더가 죽었다")

    monkeypatch.setattr("app.home.auto.start_scheduling", 터짐)
    login("지수")
    _맡기기(client, 방)
    res = client.get(f"{API}/rooms/{방.rid}/home")
    assert res.status_code == 200 and res.json()["auto_schedule"] is True
    assert _조율들(session, 방) == []
