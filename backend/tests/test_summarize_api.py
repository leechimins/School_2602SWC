"""요약·할 일 뽑기. 모델 응답을 가짜로 바꿔 끼워 검증·저장·실패 처리를 본다.

시드의 10/31 회의 "중간 발표 자료 나누기" 원문 (줄 번호):
0 지수: 오늘은 중간 발표 자료를 누가 어디까지 맡을지 정하죠.
1 민지: 발표는 제가 할게요. 슬라이드 초안은 다음 주 목요일까지 가능해요.
2 현우: 저는 프로토타입 화면을 구현할게요. 알바 때문에 평일 저녁은 어려워요.
3 서연: 디자인 시안은 제가 볼게요. 발표 대본은 아직 맡을 사람이 없어요.
4 지수: 사용자 인터뷰 정리는 제가 이번 주말까지 끝낼게요.
5 (모름): 리허설 일정은 다음 회의에서 다시 이야기해요.
이미 요약(done)과 확정 전 AI 제안 3개, 확정된 할 일 5개가 있다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.meeting.models import Meeting
from app.minutes import summarize
from app.minutes.models import Minutes, Task
from app.shared.models import Room

API = "/api/v1"
TOPIC = "중간 발표 자료 나누기"


def _room(session: Session) -> Room:
    return session.exec(select(Room)).one()


def _meeting(session: Session) -> Meeting:
    return session.exec(select(Meeting).where(Meeting.topic == TOPIC)).one()


def _url(room: Room, meeting_id: int) -> str:
    return f"{API}/rooms/{room.id}/meetings/{meeting_id}/summarize"


def _good() -> dict:
    return {
        "headline": "중간 발표 역할 분담",
        "decisions": [
            {"text": "발표는 민지가 맡는다", "lines": [1]},
            {"text": "프로토타입 화면은 현우가 맡는다", "lines": [2]},
        ],
        "discussions": [{"text": "현우는 평일 저녁이 어렵다", "lines": [2]}],
        "pendings": [{"text": "리허설 일정", "lines": [5]}],
        "tasks": [
            {"title": "슬라이드 초안 만들기", "assignee": "민지", "due_date": "2026-11-05", "lines": [1]},
            {"title": "발표 대본 담당자 정하기", "assignee": None, "due_date": None, "lines": [3]},
            {"title": "리허설 일정 잡기", "assignee": None, "due_date": None, "lines": [5]},
        ],
    }


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch):
    """summarize.request를 바꿔 끼운다. 받은 프롬프트는 prompts에 남는다."""

    class Fake:
        def __init__(self) -> None:
            self.response: dict | None = None
            self.prompts: list[str] = []

    fake = Fake()

    def request(prompt: str) -> dict | None:
        fake.prompts.append(prompt)
        return fake.response

    monkeypatch.setattr(summarize, "request", request)
    return fake


def _suggestions(session: Session, meeting: Meeting) -> list[Task]:
    return list(
        session.exec(
            select(Task)
            .where(
                Task.meeting_id == meeting.id,
                col(Task.confirmed).is_(False),
                col(Task.dropped).is_(False),
            )
            .order_by(Task.id)
        ).all()
    )


def _confirmed_ids(session: Session) -> list[int]:
    return list(
        session.exec(
            select(Task.id).where(col(Task.confirmed).is_(True)).order_by(Task.id)
        ).all()
    )


# ── 정상 ────────────────────────────────────────────────────────────


def test_요약하면_요약과_AI_제안이_회의록에_붙는다(
    client: TestClient, seeded: Session, login, fake
) -> None:
    room, meeting = _room(seeded), _meeting(seeded)
    fake.response = _good()
    login("지수")

    res = client.post(_url(room, meeting.id))

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["minutes"]["status"] == "done"
    assert body["minutes"]["headline"] == "중간 발표 역할 분담"
    assert body["minutes"]["decisions"] == ["발표는 민지가 맡는다", "프로토타입 화면은 현우가 맡는다"]
    assert body["minutes"]["discussions"] == ["현우는 평일 저녁이 어렵다"]
    assert body["minutes"]["pendings"] == ["리허설 일정"]
    suggestions = {s["title"]: s for s in body["suggestions"]}
    assert set(suggestions) == {"슬라이드 초안 만들기", "발표 대본 담당자 정하기", "리허설 일정 잡기"}
    assert suggestions["슬라이드 초안 만들기"]["assignee_name"] == "민지"
    assert suggestions["슬라이드 초안 만들기"]["due_date"] == "2026-11-05"
    assert suggestions["리허설 일정 잡기"]["assignee_user_id"] is None


def test_AI_제안은_할_일_목록에_안_나온다(
    client: TestClient, seeded: Session, login, fake
) -> None:
    room, meeting = _room(seeded), _meeting(seeded)
    fake.response = _good()
    login("지수")

    client.post(_url(room, meeting.id))
    tasks = client.get(f"{API}/rooms/{room.id}/tasks").json()

    titles = {t["title"] for t in tasks["tasks"]}
    assert "슬라이드 초안 만들기" not in titles
    assert tasks["suggestion_count"] == 3


def test_프롬프트에_원문_줄번호와_회의_날짜가_들어간다(
    client: TestClient, seeded: Session, login, fake
) -> None:
    room, meeting = _room(seeded), _meeting(seeded)
    fake.response = _good()
    login("지수")

    client.post(_url(room, meeting.id))

    prompt = fake.prompts[0]
    # "다음 주 목요일"은 시연 시계가 아니라 회의 날짜 기준으로 계산한다
    assert "회의 날짜: 2026-10-31 (토요일)" in prompt
    assert "[1] 민지: 발표는 제가 할게요." in prompt
    assert "[5] (모름): 리허설 일정은" in prompt
    assert "- 사용자 인터뷰 정리" in prompt  # 이미 확정된 할 일


def test_다시_요약하면_확정_전_제안만_바뀌고_확정된_할_일은_그대로다(
    client: TestClient, seeded: Session, login, fake
) -> None:
    room, meeting = _room(seeded), _meeting(seeded)
    old = [t.id for t in _suggestions(seeded, meeting)]
    confirmed = _confirmed_ids(seeded)
    fake.response = _good()
    login("민지")

    client.post(_url(room, meeting.id))
    client.post(_url(room, meeting.id))

    now = _suggestions(seeded, meeting)
    assert len(now) == 3  # 두 번 불러도 제안이 두 벌 쌓이지 않는다
    assert not set(old) & {t.id for t in now}
    for task_id in old:
        assert seeded.get(Task, task_id).dropped is True  # 지우지 않고 필요 없음
    assert _confirmed_ids(seeded) == confirmed


# ── 검증 ────────────────────────────────────────────────────────────


def test_근거_줄이_없는_항목은_버린다(
    client: TestClient, seeded: Session, login, fake
) -> None:
    room, meeting = _room(seeded), _meeting(seeded)
    fake.response = _good() | {
        "decisions": [
            {"text": "근거 있음", "lines": [0]},
            {"text": "없는 줄", "lines": [99]},
            {"text": "빈 근거", "lines": []},
            {"text": "참거짓은 줄 번호가 아니다", "lines": [True]},
            {"text": "근거 칸 없음"},
        ],
        "tasks": [
            {"title": "지어낸 할 일", "assignee": None, "due_date": None, "lines": [42]},
            {"title": "근거 있는 할 일", "assignee": None, "due_date": None, "lines": [3]},
        ],
    }
    login("지수")

    body = client.post(_url(room, meeting.id)).json()

    assert body["minutes"]["decisions"] == ["근거 있음"]
    assert [s["title"] for s in body["suggestions"]] == ["근거 있는 할 일"]


def test_담당자는_팀원이고_근거_줄에_나올_때만_채운다(
    client: TestClient, seeded: Session, login, fake
) -> None:
    room, meeting = _room(seeded), _meeting(seeded)
    fake.response = _good() | {
        "tasks": [
            {"title": "모르는 사람", "assignee": "철수", "due_date": None, "lines": [1]},
            # 줄 1은 민지가 말했고 현우가 나오지 않는다
            {"title": "근거와 안 맞는 담당자", "assignee": "현우", "due_date": None, "lines": [1]},
            # 줄 4는 지수가 말했다
            {"title": "말한 사람이 담당", "assignee": "지수", "due_date": None, "lines": [4]},
        ],
    }
    login("지수")

    body = client.post(_url(room, meeting.id)).json()

    by_title = {s["title"]: s["assignee_name"] for s in body["suggestions"]}
    assert by_title == {"모르는 사람": None, "근거와 안 맞는 담당자": None, "말한 사람이 담당": "지수"}


def test_날짜_꼴이_아닌_기한은_비운다(
    client: TestClient, seeded: Session, login, fake
) -> None:
    room, meeting = _room(seeded), _meeting(seeded)
    fake.response = _good() | {
        "tasks": [
            {"title": "말로 된 기한", "assignee": None, "due_date": "다음 주 목요일", "lines": [1]},
            {"title": "없는 날짜", "assignee": None, "due_date": "2026-02-30", "lines": [1]},
        ],
    }
    login("지수")

    body = client.post(_url(room, meeting.id)).json()

    assert [s["due_date"] for s in body["suggestions"]] == [None, None]


def test_이미_확정된_할_일과_같은_제목은_다시_제안하지_않는다(
    client: TestClient, seeded: Session, login, fake
) -> None:
    room, meeting = _room(seeded), _meeting(seeded)
    fake.response = _good() | {
        "tasks": [
            {"title": "사용자 인터뷰 정리", "assignee": "지수", "due_date": None, "lines": [4]},
            {"title": "새 할 일", "assignee": None, "due_date": None, "lines": [4]},
            {"title": "새 할 일", "assignee": None, "due_date": None, "lines": [4]},
        ],
    }
    login("지수")

    body = client.post(_url(room, meeting.id)).json()

    assert [s["title"] for s in body["suggestions"]] == ["새 할 일"]


def test_표현만_바꾼_확정된_할_일도_다시_제안하지_않는다(
    client: TestClient, seeded: Session, login, fake
) -> None:
    """실제 모델이 "발표 슬라이드 초안"을 "발표 슬라이드 초안 작성"으로 다시 냈다."""
    room, meeting = _room(seeded), _meeting(seeded)
    fake.response = _good() | {
        "tasks": [
            {"title": "발표 슬라이드 초안 작성", "assignee": "민지", "due_date": None, "lines": [1]},
            {"title": "디자인 시안 제작", "assignee": "서연", "due_date": None, "lines": [3]},
        ],
    }
    login("지수")

    body = client.post(_url(room, meeting.id)).json()

    assert [s["title"] for s in body["suggestions"]] == ["디자인 시안 제작"]


# ── 실패 ────────────────────────────────────────────────────────────


def _new_meeting_with_transcript(client: TestClient, room: Room) -> int:
    meeting_id = client.post(
        f"{API}/rooms/{room.id}/meetings", json={"topic": "급한 회의"}
    ).json()["id"]
    client.put(
        f"{API}/rooms/{room.id}/meetings/{meeting_id}/transcript",
        json={"text": "지수: 내일까지 자료 모아요"},
    )
    return meeting_id


@pytest.mark.parametrize(
    "response",
    [
        None,  # 모델 실패·시간 초과·JSON 깨짐 (llm.complete_json이 None을 준다)
        {"headline": "뼈대만"},  # 묶음 배열이 없다
        {"headline": "", "decisions": [], "discussions": [], "pendings": [], "tasks": []},
        {"headline": "묶음이 문자열", "decisions": "결정", "discussions": [], "pendings": [], "tasks": []},
    ],
)
def test_처음_요약이_실패하면_503이고_상태는_failed다(
    client: TestClient, seeded: Session, login, fake, response
) -> None:
    room = _room(seeded)
    login("지수")
    meeting_id = _new_meeting_with_transcript(client, room)
    fake.response = response

    res = client.post(_url(room, meeting_id))

    assert res.status_code == 503
    assert res.json()["code"] == "AGENT_TIMEOUT"
    assert res.json()["message"] == "정리를 잠시 못 했어요. 잠시 후 다시 해 주세요."
    detail = client.get(f"{API}/rooms/{room.id}/meetings/{meeting_id}").json()
    assert detail["minutes"]["status"] == "failed"
    assert len(detail["transcript"]) == 1  # 원문은 남는다


def test_다시_하기가_실패해도_전에_된_요약과_제안은_남는다(
    client: TestClient, seeded: Session, login, fake
) -> None:
    room, meeting = _room(seeded), _meeting(seeded)
    before = [t.id for t in _suggestions(seeded, meeting)]
    fake.response = None
    login("지수")

    res = client.post(_url(room, meeting.id))

    assert res.status_code == 503
    minutes = seeded.exec(select(Minutes).where(Minutes.meeting_id == meeting.id)).one()
    seeded.refresh(minutes)
    assert minutes.status == "done"
    assert minutes.headline == "중간 발표 자료를 역할별로 나눔"
    assert [t.id for t in _suggestions(seeded, meeting)] == before


def test_동시_요약에서_한쪽이_실패해도_먼저_끝난_요약은_done으로_남는다(
    client: TestClient, seeded: Session, login, monkeypatch: pytest.MonkeyPatch
) -> None:
    """이 요청이 모델을 기다리는 사이 다른 폰의 요청이 먼저 성공해 done으로 저장한 뒤,
    이 요청의 모델은 실패한다."""
    room = _room(seeded)
    login("지수")
    meeting_id = _new_meeting_with_transcript(client, room)

    def request(prompt: str) -> dict | None:
        minutes = seeded.exec(select(Minutes).where(Minutes.meeting_id == meeting_id)).one()
        minutes.headline = "다른 폰이 만든 요약"
        minutes.status = "done"
        seeded.add(minutes)
        seeded.commit()
        return None

    monkeypatch.setattr(summarize, "request", request)

    res = client.post(_url(room, meeting_id))

    assert res.status_code == 503
    detail = client.get(f"{API}/rooms/{room.id}/meetings/{meeting_id}").json()
    assert detail["minutes"]["status"] == "done"
    assert detail["minutes"]["headline"] == "다른 폰이 만든 요약"


def test_AI를_꺼도_요약은_503으로_끝난다(
    client: TestClient, seeded: Session, login
) -> None:
    """가짜를 끼우지 않는다. conftest가 LLM_ENABLED=false로 둔다."""
    room = _room(seeded)
    login("지수")
    meeting_id = _new_meeting_with_transcript(client, room)

    res = client.post(_url(room, meeting_id))

    assert res.status_code == 503


def test_실패한_뒤_다시_하면_요약된다(
    client: TestClient, seeded: Session, login, fake
) -> None:
    room = _room(seeded)
    login("지수")
    meeting_id = _new_meeting_with_transcript(client, room)
    fake.response = None
    client.post(_url(room, meeting_id))

    fake.response = _good() | {"decisions": [{"text": "자료 모으기", "lines": [0]}], "tasks": []}
    res = client.post(_url(room, meeting_id))

    assert res.status_code == 200
    assert res.json()["minutes"]["status"] == "done"
    assert res.json()["minutes"]["decisions"] == ["자료 모으기"]


# ── 막는 경우 ────────────────────────────────────────────────────────


def test_원문이_없으면_409다(client: TestClient, seeded: Session, login, fake) -> None:
    room = _room(seeded)
    login("지수")
    meeting_id = client.post(
        f"{API}/rooms/{room.id}/meetings", json={"topic": "빈 회의"}
    ).json()["id"]

    res = client.post(_url(room, meeting_id))

    assert res.status_code == 409
    assert res.json()["code"] == "NO_TRANSCRIPT"
    assert fake.prompts == []  # 모델을 부르지 않는다


def test_팀원이_아니면_요약할_수_없다(
    client: TestClient, seeded: Session, login, fake
) -> None:
    from app.shared.models import User

    seeded.add(User(name="외부인"))
    seeded.commit()
    login("외부인")

    res = client.post(_url(_room(seeded), _meeting(seeded).id))

    assert res.status_code == 403
    assert fake.prompts == []
