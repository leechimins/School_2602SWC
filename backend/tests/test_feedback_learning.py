"""수락·거절 때 남긴 한 줄이 내 선호를 바꾼다(app/me/learn.py).

지켜야 하는 것:
- 바뀌면 반드시 기록이 남고 응답에 실린다. 말없이 바꾸지 않는다.
- 사람이 직접 적은 피하는 시간(알바 등)을 피드백 한 줄이 덮지 않는다.
- 되돌리면 원래 값으로. 그 뒤 또 바뀌었으면 덮지 않는다(409).
- 모델이 애매하게 답하면 아무것도 안 바꾼다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.me import learn
from app.me.models import Preference
from app.meeting.models import PreferenceChange
from app.shared.enums import Daypart, Mode

from test_proposal_api import API, MON, LLM을_끈다, _응답, _합의된_회의, 방, 팀  # noqa: F401

거절_오전 = {
    "field": "avoid", "weekdays": [0], "start": 540, "end": 720,
    "sentence": "월요일 오전은 수업 직후라 어렵습니다",
    "summary": "다음부터 월요일 오전은 피할게요",
}


def _answer(monkeypatch: pytest.MonkeyPatch, payload: object) -> list[str]:
    """모델이 이렇게 답했다고 친다. 보낸 프롬프트를 모아 돌려준다."""
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    prompts: list[str] = []

    def fake(prompt: str, **_: object) -> object:
        prompts.append(prompt)
        return payload

    monkeypatch.setattr(learn.llm, "complete_json", fake)
    return prompts


def _pref(session: Session, user_id: int) -> Preference | None:
    session.expire_all()
    return session.exec(select(Preference).where(Preference.user_id == user_id)).first()


# ── 수락·거절에서 ───────────────────────────────────────────────────


def test_거절하며_남긴_한_줄이_피하는_시간이_된다(
    client: TestClient, session: Session, 방: 팀, login, monkeypatch: pytest.MonkeyPatch
) -> None:
    meeting = _합의된_회의(session, 방)
    prompts = _answer(monkeypatch, 거절_오전)
    login("민지")
    r = _응답(client, 방.room_id, meeting.id, accept=False, feedback="오전은 수업 끝나자마자라 힘들어요")
    assert r.status_code == 200  # type: ignore[attr-defined]
    change = r.json()["preference_change"]  # type: ignore[attr-defined]
    assert change["summary"] == "다음부터 월요일 오전은 피할게요"
    assert change["field"] == "avoid" and change["before"] is None

    pref = _pref(session, 방.민지.id)  # type: ignore[arg-type]
    assert pref is not None
    assert (pref.avoid_weekdays, pref.avoid_start_min, pref.avoid_end_min) == ([0], 540, 720)
    assert pref.avoid_polished == "월요일 오전은 수업 직후라 어렵습니다"
    # 모델은 회의 요일·시각과 수락/거절을 안다. "그날"이 언제인지 알아야 한다.
    assert "월요일 14:00" in prompts[0] and "거절" in prompts[0]


def test_시간과_상관없는_말이면_아무것도_안_바뀐다(
    client: TestClient, session: Session, 방: 팀, login, monkeypatch: pytest.MonkeyPatch
) -> None:
    meeting = _합의된_회의(session, 방)
    _answer(monkeypatch, {"field": None, "summary": ""})
    login("민지")
    r = _응답(client, 방.room_id, meeting.id, feedback="자료는 제가 준비할게요")
    assert r.json()["preference_change"] is None  # type: ignore[attr-defined]
    assert session.exec(select(PreferenceChange)).all() == []


def test_모델이_꺼져_있어도_답은_그대로_된다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    meeting = _합의된_회의(session, 방)
    login("민지")
    r = _응답(client, 방.room_id, meeting.id, accept=False, feedback="오전은 힘들어요")
    assert r.status_code == 200  # type: ignore[attr-defined]
    assert r.json()["preference_change"] is None  # type: ignore[attr-defined]


# ── 해석 검사 ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "payload",
    [
        {**거절_오전, "start": 720, "end": 540},  # 뒤집힌 구간
        {**거절_오전, "weekdays": [9]},  # 없는 요일
        {**거절_오전, "sentence": ""},  # 팀에 보일 문장이 없다
        {"field": "dayparts", "dayparts": ["brunch"], "summary": "x"},
        {"field": "mode_pref", "mode_pref": "hybrid", "summary": "x"},
        {"field": "salary", "summary": "x"},
        {**거절_오전, "summary": ""},
    ],
)
def test_이상한_답은_버린다(monkeypatch: pytest.MonkeyPatch, payload: dict) -> None:
    _answer(monkeypatch, payload)
    assert learn.interpret("아무 말", MON, accepted=False) is None


# ── 덮지 않기 ───────────────────────────────────────────────────────


def test_사람이_적은_다른_시각의_피하는_시간을_덮지_않는다(
    session: Session, 방: 팀, monkeypatch: pytest.MonkeyPatch
) -> None:
    session.add(Preference(
        user_id=방.민지.id, avoid_raw="금요일 저녁 알바", avoid_polished="금요일 저녁은 어렵습니다",
        avoid_weekdays=[4], avoid_start_min=1080, avoid_end_min=1320,
    ))
    session.commit()
    _answer(monkeypatch, 거절_오전)
    assert learn.learn(session, 방.민지.id, 1, "오전 힘들어요", MON, accepted=False) is None  # type: ignore[arg-type]
    pref = _pref(session, 방.민지.id)  # type: ignore[arg-type]
    assert pref is not None and pref.avoid_weekdays == [4] and pref.avoid_start_min == 1080


def test_같은_시각이면_요일만_더한다(
    session: Session, 방: 팀, monkeypatch: pytest.MonkeyPatch
) -> None:
    session.add(Preference(
        user_id=방.민지.id, avoid_raw="목요일 오전 수업", avoid_polished="목요일 오전은 어렵습니다",
        avoid_weekdays=[3], avoid_start_min=540, avoid_end_min=720,
    ))
    session.commit()
    _answer(monkeypatch, 거절_오전)
    change = learn.learn(session, 방.민지.id, None, "월 오전도 힘들어요", MON, accepted=False)  # type: ignore[arg-type]
    assert change is not None
    assert change.before == "목요일 오전 수업"
    pref = _pref(session, 방.민지.id)  # type: ignore[arg-type]
    assert pref is not None and pref.avoid_weekdays == [0, 3]
    assert pref.avoid_polished == "목요일 오전은 어렵습니다 / 월요일 오전은 수업 직후라 어렵습니다"


# ── 목록과 되돌리기 ─────────────────────────────────────────────────


def _시간대_바꾸기(session: Session, user_id: int, parts: list[str], monkeypatch) -> PreferenceChange:
    _answer(monkeypatch, {"field": "dayparts", "dayparts": parts, "summary": "다음부터 오후로 잡을게요"})
    change = learn.learn(session, user_id, None, "오후가 좋아요", MON, accepted=True)
    assert change is not None
    return change


def test_되돌리면_원래_시간대로(
    client: TestClient, session: Session, 방: 팀, login, monkeypatch: pytest.MonkeyPatch
) -> None:
    session.add(Preference(user_id=방.민지.id, dayparts=[Daypart.FORENOON], mode_pref=Mode.ANY))
    session.commit()
    change = _시간대_바꾸기(session, 방.민지.id, ["afternoon", "forenoon"], monkeypatch)  # type: ignore[arg-type]
    assert (change.before, change.after) == ("forenoon", "forenoon,afternoon")

    login("민지")
    listed = client.get(f"{API}/me/preference-changes").json()
    assert [c["id"] for c in listed] == [change.id]

    for _ in range(2):  # 두 번 눌러도 그대로
        r = client.post(f"{API}/me/preference-changes/{change.id}/undo")
        assert r.status_code == 200 and r.json()["reverted"] is True
    pref = _pref(session, 방.민지.id)  # type: ignore[arg-type]
    assert pref is not None and pref.dayparts == [Daypart.FORENOON]


def test_그_뒤에_또_바뀌었으면_되돌리지_않는다(
    client: TestClient, session: Session, 방: 팀, login, monkeypatch: pytest.MonkeyPatch
) -> None:
    첫 = _시간대_바꾸기(session, 방.민지.id, ["afternoon"], monkeypatch)  # type: ignore[arg-type]
    _시간대_바꾸기(session, 방.민지.id, ["evening"], monkeypatch)  # type: ignore[arg-type]
    login("민지")
    r = client.post(f"{API}/me/preference-changes/{첫.id}/undo")
    assert r.status_code == 409
    pref = _pref(session, 방.민지.id)  # type: ignore[arg-type]
    assert pref is not None and pref.dayparts == [Daypart.EVENING]


def test_남의_변경은_못_되돌린다(
    client: TestClient, session: Session, 방: 팀, login, monkeypatch: pytest.MonkeyPatch
) -> None:
    change = _시간대_바꾸기(session, 방.민지.id, ["afternoon"], monkeypatch)  # type: ignore[arg-type]
    login("현우")
    assert client.post(f"{API}/me/preference-changes/{change.id}/undo").status_code == 404
    assert client.get(f"{API}/me/preference-changes").json() == []
