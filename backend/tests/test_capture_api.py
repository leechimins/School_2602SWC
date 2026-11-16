"""에브리타임 시간표 캡처 읽기·확정 (#66).

모델(llm.complete_json_image)은 가짜로 바꿔 끼운다. 이미지는 실제 캡처 대신 에브리타임과
같은 모양(회색 격자, 요일 열 5개, 한 시간 135px, 색칠 칸)을 Pillow로 그려 쓴다 —
실제 캡처에는 교수 이름이 있어 저장소에 두지 않는다. 실제 캡처로 잰 평가는
_local/AI-품질/캡처/에 있다.
"""

from __future__ import annotations

import io
from datetime import datetime

import pytest
from PIL import Image, ImageDraw
from sqlmodel import Session, select

from app.integration import capture, capture_grid
from app.integration.capture import Capture, CapturedClass
from app.me.models import ScheduleItem
from app.shared import demo_clock, llm
from app.shared.base import KST
from app.shared.enums import ScheduleSource
from app.shared.models import User

API = "/api/v1/me/integrations/everytime"
TODAY = datetime(2026, 11, 10, 9, 0, tzinfo=KST)

# ── 에브리타임 모양 그림 ─────────────────────────────────────────────
# 11/16 실제 캡처(1179×2556)에서 잰 값: 격자선 #EDEDED, 표 위 테두리 y=393,
# 요일 머리 아래 선 y=453(첫 시각 9시), 한 시간 135px, 세로선 x=24·84·300·516·732·948·1152.
LINE = (237, 237, 237)
TOP, HEAD, HOUR = 393, 453, 135
XS = [24, 84, 300, 516, 732, 948, 1152]
ORIGIN = HEAD + 3  # 선 두께 3


def draw(blocks: list[tuple[int, int, int, tuple[int, int, int]]], *, hours: int = 9) -> bytes:
    """blocks: (요일, 시작 분, 끝 분, 색). 첫 시각은 9시."""
    w, h = 1179, 2556
    im = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(im)
    bottom = HEAD + HOUR * hours
    for y in [TOP, *(HEAD + HOUR * k for k in range(hours + 1))]:
        d.rectangle([XS[0], y, XS[-1] + 2, y + 2], fill=LINE)
    for x in XS:
        d.rectangle([x, TOP, x + 2, bottom + 2], fill=LINE)
    for day, start, end, color in blocks:
        x0, x1 = XS[day + 1] + 3, XS[day + 2] - 1
        y0 = ORIGIN + (start - 540) * HOUR / 60
        y1 = ORIGIN + (end - 540) * HOUR / 60
        d.rectangle([x0, round(y0), x1, round(y1) - 1], fill=color)
        # 과목명 글씨(흰색)는 칸 왼쪽에서 조금 떨어져 시작한다
        d.rectangle([x0 + 8, round(y0) + 10, x1 - 10, round(y0) + 40], fill=(255, 255, 255))
    # 화면 아래 시트·탭 영역(표 밖)
    d.rectangle([0, bottom + 200, w, h], fill=(250, 250, 250))
    out = io.BytesIO()
    im.save(out, format="PNG")
    return out.getvalue()


RED, GREEN, TEAL = (240, 136, 120), (166, 202, 112), (124, 208, 190)

# 월 10:30-11:45 알고리즘, 월 12:00-13:15 알고리즘, 목 10:30-13:15 모바일응용, 목 13:30-14:45 DB
IMAGE_BLOCKS = [
    (0, 630, 705, RED),
    (0, 720, 795, RED),
    (3, 630, 795, GREEN),
    (3, 810, 885, TEAL),
]

# 모델은 위치를 뭉갠다(실제 평가에서 본 모양: 끝을 정각·30분으로)
AI_ANSWER = {
    "is_everytime": True,
    "year": 2026,
    "semester": "2",
    "classes": [
        {"title": "알고리즘", "day": "월", "start": "10:30", "end": "12:00"},
        {"title": "알고리즘", "day": "월", "start": "12:00", "end": "13:30"},
        {"title": "모바일응용", "day": "목", "start": "10:30", "end": "13:30"},
        {"title": "데이터베이스 프로그래밍", "day": "목", "start": "13:30", "end": "15:00"},
    ],
}


class FakeModel:
    def __init__(self) -> None:
        self.answer: dict | None = dict(AI_ANSWER)
        self.calls: list[tuple[bytes, str]] = []

    def __call__(self, prompt: str, image: bytes, *, mime: str = "image/png", **_: object) -> dict | None:
        self.calls.append((image, mime))
        return self.answer


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> FakeModel:
    fake = FakeModel()
    monkeypatch.setattr(llm, "complete_json_image", fake)
    return fake


@pytest.fixture
def jisu(seeded: Session, login) -> User:
    demo_clock.set_clock(seeded, TODAY)
    seeded.commit()
    login("지수")
    return seeded.exec(select(User).where(User.name == "지수")).one()


def _preview(client, image: bytes, mime: str = "image/png"):
    return client.post(f"{API}/capture/preview", content=image, headers={"Content-Type": mime})


def _everytime_rows(session: Session, user_id: int) -> list[ScheduleItem]:
    session.expire_all()
    return list(
        session.exec(
            select(ScheduleItem)
            .where(ScheduleItem.user_id == user_id, ScheduleItem.source == ScheduleSource.EVERYTIME)
            .order_by(ScheduleItem.weekday, ScheduleItem.start_min)
        )
    )


def _snapshot(session: Session, user_id: int) -> list[tuple]:
    return [(r.id, r.title, r.weekday, r.start_min, r.end_min) for r in _everytime_rows(session, user_id)]


# ── 모델 답 거르기 (단위) ─────────────────────────────────────────────


def test_모델_답을_요일_번호와_5분_단위_분으로_바꾼다():
    got = capture.parse_answer(
        {
            "is_everytime": True,
            "year": "2024",
            "semester": "2학기",
            "classes": [
                {"title": "  객체 \n 프로그래밍 ", "day": "목요일", "start": "10:31", "end": "11:47"},
                {"title": "", "day": "금", "start": "9:00", "end": "10:15"},
            ],
        }
    )
    assert got.year == 2024 and got.semester == "2"
    assert got.classes == (
        CapturedClass("객체 프로그래밍", 3, 630, 705),
        CapturedClass("수업", 4, 540, 615),
    )


def test_틀린_칸은_버리고_나머지는_남긴다():
    got = capture.parse_answer(
        {
            "is_everytime": True,
            "classes": [
                {"title": "요일 없음", "day": "x", "start": "10:00", "end": "11:00"},
                {"title": "거꾸로", "day": "월", "start": "11:00", "end": "10:00"},
                {"title": "모양 틀림", "day": "월", "start": "열시", "end": "11:00"},
                {"title": "하루 넘음", "day": "월", "start": "23:00", "end": "25:00"},
                "문자열",
                {"title": "정상", "day": "화", "start": "10:00", "end": "11:15"},
                {"title": "정상 두 번", "day": "화", "start": "10:00", "end": "11:15"},
            ],
        }
    )
    assert got.classes == (CapturedClass("정상", 1, 600, 675),)
    assert got.year is None and got.semester is None


def test_에브리타임이_아니면_NotEverytime():
    with pytest.raises(capture.NotEverytime):
        capture.parse_answer({"is_everytime": False, "classes": []})
    with pytest.raises(capture.NotEverytime):
        capture.parse_answer({"classes": []})  # 답을 안 했으면 받지 않는다


def test_classes가_목록이_아니면_ReadFailed():
    with pytest.raises(capture.ReadFailed):
        capture.parse_answer({"is_everytime": True, "classes": "없음"})


# ── 격자 재기 (단위) ──────────────────────────────────────────────────


def test_격자에서_칸의_요일과_분을_잰다():
    grid = capture_grid.measure(draw(IMAGE_BLOCKS))
    assert grid is not None and grid.days == 5
    got = [(b.weekday, round(540 + b.start_off), round(540 + b.end_off)) for b in grid.blocks]
    assert got == [(0, 630, 705), (0, 720, 795), (3, 630, 795), (3, 810, 885)]


def test_붙어_있는_칸은_색이_바뀌면_나눈다():
    grid = capture_grid.measure(draw([(1, 600, 675, RED), (1, 675, 750, TEAL)]))
    got = [(b.weekday, round(540 + b.start_off), round(540 + b.end_off)) for b in grid.blocks]
    assert got == [(1, 600, 675), (1, 675, 750)]


def _recolor(image: bytes, kind: str) -> bytes:
    from PIL import ImageOps

    im = Image.open(io.BytesIO(image)).convert("RGB")
    im = ImageOps.grayscale(im).convert("RGB") if kind == "gray" else ImageOps.invert(im)
    out = io.BytesIO()
    im.save(out, format="PNG")
    return out.getvalue()


@pytest.mark.parametrize("kind", ["gray", "invert"])
def test_테마가_바뀌어도_칸을_잰다(kind):
    # 에브리타임은 테마로 칸 색이 바뀌고 다크 모드가 있다. 색을 박아 두지 않는다.
    # 노랑·빨강은 흑백에서 비슷한 회색이 되는데, 붙어 있어도 나뉘어야 한다.
    yellow = (233, 195, 104)
    image = draw([*IMAGE_BLOCKS, (1, 540, 630, RED), (1, 630, 690, yellow)])
    grid = capture_grid.measure(_recolor(image, kind))
    got = [(b.weekday, round(540 + b.start_off), round(540 + b.end_off)) for b in grid.blocks]
    assert got == [(0, 630, 705), (0, 720, 795), (1, 540, 630), (1, 630, 690), (3, 630, 795), (3, 810, 885)]


def test_격자가_없는_그림이면_None():
    out = io.BytesIO()
    Image.new("RGB", (800, 1200), (30, 30, 30)).save(out, format="PNG")
    assert capture_grid.measure(out.getvalue()) is None
    assert capture_grid.measure(b"not an image") is None


def test_위치는_격자_과목명은_모델():
    ai = capture.parse_answer(AI_ANSWER)
    got = capture.merge(ai, capture_grid.measure(draw(IMAGE_BLOCKS)))
    assert [(c.title, c.weekday, c.start_min, c.end_min) for c in got.classes] == [
        ("알고리즘", 0, 630, 705),
        ("알고리즘", 0, 720, 795),
        ("모바일응용", 3, 630, 795),
        ("데이터베이스 프로그래밍", 3, 810, 885),
    ]
    assert (got.year, got.semester) == (2026, "2")


def _rows(c: Capture) -> list[tuple]:
    return [(x.title, x.weekday, x.start_min, x.end_min) for x in c.classes]


def test_수업_목록은_모델_것이고_격자만_찾은_칸은_넣지_않는다():
    # 격자는 시각만 다듬는다. 격자 때문에 수업이 생기거나 빠지면 안 된다.
    ai = Capture(
        2024,
        "2",
        (
            CapturedClass("알고리즘", 0, 630, 720),
            CapturedClass("격자에 없음", 2, 600, 660),  # 겹치는 격자 칸이 없다 → 모델 시각 그대로
        ),
    )
    grid = capture_grid.measure(draw([(0, 630, 705, RED), (4, 540, 615, TEAL)]))  # 금요일 칸은 모델에 없다
    got = capture.merge(ai, grid)
    assert _rows(got) == [
        ("알고리즘", 0, 630, 705),
        ("격자에 없음", 2, 600, 660),
    ]


def test_격자_칸_하나에_모델_칸이_둘이면_모델_시각_그대로():
    # 같은 색 칸 두 개가 붙어 있으면 격자는 긴 칸 하나로 본다. 어느 쪽 시각인지 모르니 손대지 않는다.
    ai = Capture(
        2024,
        "2",
        (
            CapturedClass("앞 수업", 1, 540, 630),
            CapturedClass("뒤 수업", 1, 630, 690),
        ),
    )
    grid = capture_grid.measure(draw([(1, 540, 690, RED)]))
    assert _rows(capture.merge(ai, grid)) == _rows(ai)


def test_같은_과목을_쪼개_읽었으면_격자_칸_하나로_합친다():
    # 모델이 165분 칸 하나를 같은 과목명 두 칸으로 읽은 경우(11/16 반전 캡처)
    ai = Capture(
        2024,
        "2",
        (
            CapturedClass("모바일응용", 3, 630, 720),
            CapturedClass("모바일 응용", 3, 720, 780),
            CapturedClass("다른 요일", 0, 630, 705),
        ),
    )
    grid = capture_grid.measure(draw([(3, 630, 795, GREEN), (0, 630, 705, RED)]))
    assert _rows(capture.merge(ai, grid)) == [
        ("다른 요일", 0, 630, 705),
        ("모바일응용", 3, 630, 795),
    ]


def test_조금_어긋나_이웃_칸에_걸쳐도_서로_가장_많이_겹치는_칸끼리_짝짓는다():
    # 11/16 실제: 15:00~16:15·16:30~17:45 두 칸을 15:00~16:00·16:00~17:00으로 읽음.
    # 두 번째가 두 격자 칸에 걸치지만 서로 가장 많이 겹치는 짝은 하나로 정해진다.
    ai = Capture(
        2026,
        "2",
        (
            CapturedClass("빅데이터처리", 0, 900, 960),
            CapturedClass("빅데이터처리", 0, 960, 1020),
        ),
    )
    grid = capture_grid.measure(draw([(0, 900, 975, RED), (0, 990, 1065, RED)]))
    assert _rows(capture.merge(ai, grid)) == [
        ("빅데이터처리", 0, 900, 975),
        ("빅데이터처리", 0, 990, 1065),
    ]


def test_모델_칸_하나가_격자_칸_둘에_걸치면_모델_시각_그대로():
    ai = Capture(2024, "2", (CapturedClass("긴 수업", 0, 630, 810),))
    grid = capture_grid.measure(draw([(0, 630, 705, RED), (0, 720, 795, TEAL)]))
    assert _rows(capture.merge(ai, grid)) == [("긴 수업", 0, 630, 810)]


def test_격자를_못_찾으면_모델_답_그대로():
    ai = capture.parse_answer(AI_ANSWER)
    assert capture.merge(ai, None) == ai


def test_모델에는_원본을_그대로_보낸다(model):
    # 잘라 보내 봐도 토큰이 같았고(11/16), 격자가 칸을 놓치면 그 칸까지 잘린다
    image = draw(IMAGE_BLOCKS)
    capture.read(image, "image/png")
    assert model.calls == [(image, "image/png")]
