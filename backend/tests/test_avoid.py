"""온보딩 질문 4 — "꼭 피하고 싶은 시간대가 있어요?"

한 줄에서 두 가지가 나온다. 다듬은 문장(발언에 씀)과 구간(점수에 씀).
모델은 여기서 한 번만 부르고, 조율마다 다시 부르지 않는다.

**구조를 못 뽑는 경우가 흔하다.** 그때 억지로 숫자를 만들면 엉뚱한 시간이
거절되므로 문장만 남기고 점수는 안 건드린다. 이 파일이 주로 보는 게 그
"못 뽑았을 때" 쪽이다 — 잘 뽑혔을 때보다 틀리기 쉽다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.me import avoid
from app.me.models import Preference
from app.meeting.scorer import AVOID_PENALTY, score_for
from app.shared.base import KST
from app.shared.models import User

API = "/api/v1"
# 2026-11-20은 금요일(weekday 4).
금 = datetime(2026, 11, 20, tzinfo=KST)


def _answer(monkeypatch: pytest.MonkeyPatch, payload: object) -> None:
    """모델이 이렇게 답했다고 치고 돌린다. 실제 호출은 나가지 않는다."""
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(avoid.llm, "complete_json", lambda *a, **k: payload)


# ── 해석 ────────────────────────────────────────────────────────────


def test_문장과_구간을_한_번에_뽑는다(monkeypatch: pytest.MonkeyPatch) -> None:
    _answer(monkeypatch, {
        "sentence": "금요일 저녁은 개인 일정이 있어 어렵습니다",
        "weekdays": [4], "start": 1080, "end": 1320,
    })
    got = avoid.interpret("금요일 저녁은 알바 끝나고 바로라 피하고 싶어요")
    assert got is not None
    assert got.polished == "금요일 저녁은 개인 일정이 있어 어렵습니다"
    assert got.weekdays == [4]
    assert (got.start_min, got.end_min) == (1080, 1320)


def test_구간을_못_뽑으면_문장만_남는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """"너무 이른 시간은 싫어요" 같은 말. 요일이 없다.

    문장은 발언에 쓰이므로 값이 없는 게 아니다. 점수만 안 건드린다.
    """
    _answer(monkeypatch, {
        "sentence": "이른 시간은 어렵습니다", "weekdays": None, "start": None, "end": None,
    })
    got = avoid.interpret("너무 이른 시간은 싫어요")
    assert got is not None
    assert got.polished == "이른 시간은 어렵습니다"
    assert got.weekdays is None and got.start_min is None and got.end_min is None


@pytest.mark.parametrize(
    "payload",
    [
        {"sentence": "x", "weekdays": [7], "start": 600, "end": 700},      # 요일 범위 밖
        {"sentence": "x", "weekdays": [4], "start": 700, "end": 600},      # 뒤집힘
        {"sentence": "x", "weekdays": [4], "start": 600, "end": 2000},     # 분 범위 밖
        {"sentence": "x", "weekdays": [4], "start": "저녁", "end": 1320},  # 숫자가 아님
        {"sentence": "x", "weekdays": "금요일", "start": 1080, "end": 1320},
        {"sentence": "x", "weekdays": [], "start": 1080, "end": 1320},
    ],
)
def test_구간이_이상하면_셋_다_버린다(
    monkeypatch: pytest.MonkeyPatch, payload: dict
) -> None:
    """반쯤 맞는 구간이 가장 나쁘다.

    요일만 맞고 시각이 틀리면 그 요일 하루가 통째로 벌점을 받는다.
    """
    _answer(monkeypatch, payload)
    got = avoid.interpret("아무 말")
    assert got is not None
    assert got.polished == "x"
    assert got.weekdays is None and got.start_min is None and got.end_min is None


def test_모델이_실패하면_None이다(monkeypatch: pytest.MonkeyPatch) -> None:
    """원문을 복사해 넣지 않는다 — 다듬지 않은 말이 팀에 나가면 안 된다."""
    _answer(monkeypatch, None)
    assert avoid.interpret("금요일 저녁은 알바라서요") is None


def test_빈_줄이면_모델을_안_부른다(monkeypatch: pytest.MonkeyPatch) -> None:
    def 부르면_터짐(*a: object, **k: object) -> None:
        raise AssertionError("빈 줄에는 모델을 부르면 안 된다")

    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setattr(avoid.llm, "complete_json", 부르면_터짐)
    assert avoid.interpret(None) is None
    assert avoid.interpret("   ") is None


# ── 점수 ────────────────────────────────────────────────────────────


def _pref(**kw: object) -> Preference:
    base = {"user_id": 1, "avoid_polished": "금요일 저녁은 개인 일정이 있어 어렵습니다",
            "avoid_weekdays": [4], "avoid_start_min": 1080, "avoid_end_min": 1320}
    base.update(kw)
    return Preference(**base)  # type: ignore[arg-type]


def _score(hour: int, pref: Preference, hours: int = 2) -> int:
    start = 금.replace(hour=hour)
    return score_for(start, start + timedelta(hours=hours), 1, pref, []).score


def test_피하고_싶은_구간에_걸리면_벌점이_붙는다() -> None:
    assert _score(18, _pref()) == 1 + AVOID_PENALTY


def test_걸치기만_해도_붙는다() -> None:
    """17~19시 회의는 "18시 이후는 피하고 싶다"는 사람에게 실제로 걸린다.

    시작만 보는 시간대 선호와 다른 점이다.
    """
    assert _score(17, _pref()) == 1 + AVOID_PENALTY


def test_끝나는_시각에_딱_닿으면_안_붙는다() -> None:
    """16~18시 회의는 18시에 끝난다. 그 구간 안에 있던 적이 없다."""
    assert _score(16, _pref()) == 1


def test_다른_요일이면_안_붙는다() -> None:
    assert _score(18, _pref(avoid_weekdays=[0])) == 1


def test_구간이_없으면_점수를_안_건드린다() -> None:
    """문장만 뽑힌 경우. 발언에는 쓰이지만 점수에는 안 들어간다."""
    쪽지만 = _pref(avoid_weekdays=None, avoid_start_min=None, avoid_end_min=None)
    assert _score(18, 쪽지만) == 1


def test_이유로_다듬은_문장이_나간다() -> None:
    """원문이 아니라 다듬은 문장이다. 사적인 사유가 팀에 나가면 안 된다."""
    start = 금.replace(hour=18)
    cost = score_for(start, start + timedelta(hours=2), 1, _pref(), [])
    assert cost.reason == "금요일 저녁은 개인 일정이 있어 어렵습니다"


def test_거절선을_넘길_수_있다() -> None:
    """이게 이 기능을 넣은 이유다.

    전에는 올 수 있는 사람의 최대 점수가 1+2+1 = 4라서, 빠듯함과 시간대
    밖이 **동시에** 걸릴 때만 거절이 났다. 그래서 라운드 2·3이 돌 일이
    거의 없었다. 피하고 싶은 시간이 들어오면 하나만 더 겹쳐도 넘는다.
    """
    from app.shared.enums import Daypart

    이른오전만_좋아함 = _pref(dayparts=[Daypart.FORENOON])
    # 금요일 18시: 피하고 싶은 구간(+2) + 좋다고 한 시간대 밖(+1)
    assert _score(18, 이른오전만_좋아함) == 1 + AVOID_PENALTY + 1 >= 4


# ── 온보딩에서 끝까지 ───────────────────────────────────────────────


def test_온보딩이_구간까지_저장한다(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    session.add(User(name="지수"))
    session.commit()
    _answer(monkeypatch, {
        "sentence": "금요일 저녁은 개인 일정이 있어 어렵습니다",
        "weekdays": [4], "start": 1080, "end": 1320,
    })
    assert client.post(f"{API}/sessions", json={"name": "지수"}).status_code == 201

    body = client.post(
        f"{API}/me/onboarding/interpret",
        json={"avoid_raw": "금요일 저녁은 알바 끝나고 바로라 피하고 싶어요"},
    ).json()

    assert body["avoid_polished"] == "금요일 저녁은 개인 일정이 있어 어렵습니다"
    assert body["avoid_weekdays"] == [4]
    assert body["avoid_start_min"] == 1080

    saved = session.exec(select(Preference)).one()
    assert saved.avoid_end_min == 1320
    # 원문도 남는다. 사람이 자기가 뭐라고 적었는지 볼 수 있어야 한다.
    assert saved.avoid_raw == "금요일 저녁은 알바 끝나고 바로라 피하고 싶어요"
