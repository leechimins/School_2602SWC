"""발언 속 시간은 늘 한국 시간이다. DB가 UTC로 돌려줘도(Render) 9시간 어긋나면 안 된다."""

from datetime import datetime, timezone

from app.meeting.prompts import when
from app.shared.base import KST


def test_UTC로_받은_시각도_한국_시간으로_쓴다() -> None:
    start = datetime(2026, 11, 18, 3, 0, tzinfo=timezone.utc)  # = 한국 12:00
    end = datetime(2026, 11, 18, 4, 30, tzinfo=timezone.utc)
    assert when(start, end) == "11월 18일(수) 12:00–13:30"


def test_UTC로는_전날인_아침도_한국_날짜로() -> None:
    start = datetime(2026, 11, 17, 23, 0, tzinfo=timezone.utc)  # = 한국 11/18 08:00
    end = datetime(2026, 11, 18, 0, 0, tzinfo=timezone.utc)
    assert when(start, end) == "11월 18일(수) 08:00–09:00"


def test_한국_시간은_그대로() -> None:
    assert when(datetime(2026, 11, 18, 12, tzinfo=KST), datetime(2026, 11, 18, 13, 30, tzinfo=KST)) == "11월 18일(수) 12:00–13:30"
