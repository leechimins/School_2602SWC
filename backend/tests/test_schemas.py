"""시각 피커가 분으로 바뀌는지, 이상한 값이 막히는지.

DB도 서버도 필요 없다. 온보딩에서 유일하게 계산이 있는 곳이라 따로 둔다.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.me.schemas import Hour12, OnboardingIn


@pytest.mark.parametrize(
    ("hour12", "ampm", "minute", "expected"),
    [
        (9, "am", 0, 540),  # 9:00
        (6, "pm", 0, 1080),  # 18:00
        (12, "am", 0, 0),  # 자정. 12를 0으로 돌려야 한다
        (12, "pm", 0, 720),  # 정오. 12 그대로다
        (12, "pm", 30, 750),  # 12:30
        (9, "am", 30, 570),  # 9:30
        (11, "pm", 30, 1410),  # 23:30 — 하루 안에서 가장 늦은 값
    ],
)
def test_피커가_자정부터_분으로_바뀐다(
    hour12: int, ampm: str, minute: int, expected: int
) -> None:
    assert Hour12(hour12=hour12, ampm=ampm, minute=minute).to_minutes() == expected


@pytest.mark.parametrize(
    "bad",
    [
        {"hour12": 13, "ampm": "am"},  # 12시간제라 13이 없다
        {"hour12": 0, "ampm": "am"},  # 0시도 없다 — 자정은 12am이다
        {"hour12": 9, "ampm": "am", "minute": 15},  # 30분 단위만 받는다
        {"hour12": 9, "ampm": "AM"},  # 대문자는 안 받는다
        {"hour12": 9, "ampm": "오전"},
    ],
)
def test_피커가_이상한_값을_막는다(bad: dict) -> None:
    with pytest.raises(ValidationError):
        Hour12(**bad)


def test_네_칸을_다_비워도_된다() -> None:
    """브리프: "필수 항목은 없습니다. 네 개를 다 비워도 다음으로 넘어갑니다"."""
    answers = OnboardingIn()
    assert answers.day_start is None
    assert answers.mode_pref is None
    assert answers.dayparts is None
    assert answers.avoid_raw is None


# 시작·끝 범위가 거꾸로인 경우는 여기서 보지 않는다. PATCH가 한쪽만 보낼 수
# 있어서 저장된 값과 합친 뒤에야 알 수 있고, 그 검사는 라우터에 있다.
# → test_me_api.py의 test_시작이_끝보다_늦으면_400이_온다
