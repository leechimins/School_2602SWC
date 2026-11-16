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
from app.integration import everytime_service as service
from app.integration.capture import Capture, CapturedClass
from app.me.models import ScheduleItem
from app.shared import demo_clock, llm
from app.shared.base import KST
from app.shared.enums import Recurrence, ScheduleKind, ScheduleSource
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


# ── 미리보기 API ─────────────────────────────────────────────────────


def test_미리보기는_읽은_수업만_돌려주고_저장하지_않는다(client, model, jisu, seeded):
    before = _snapshot(seeded, jisu.id)  # 시드에 에브리타임 수업이 이미 있다
    res = _preview(client, draw(IMAGE_BLOCKS))
    assert res.status_code == 200, res.text
    assert res.json() == {
        "classes": [
            {"title": "알고리즘", "weekday": 0, "start_min": 630, "end_min": 705},
            {"title": "알고리즘", "weekday": 0, "start_min": 720, "end_min": 795},
            {"title": "모바일응용", "weekday": 3, "start_min": 630, "end_min": 795},
            {"title": "데이터베이스 프로그래밍", "weekday": 3, "start_min": 810, "end_min": 885},
        ],
        "year": 2026,
        "semester": "2",
        "term": "2026년 2학기",
    }
    assert _snapshot(seeded, jisu.id) == before
    assert service.get_link(seeded, jisu.id) is None


def test_수업을_못_읽으면_빈_목록(client, model, jisu):
    model.answer = {"is_everytime": True, "year": 2026, "semester": "2", "classes": []}
    res = _preview(client, draw([]))
    assert res.status_code == 200
    assert res.json()["classes"] == []


def test_에브리타임_시간표가_아니면_400(client, model, jisu):
    model.answer = {"is_everytime": False, "classes": []}
    res = _preview(client, draw([]))
    assert res.status_code == 400
    assert res.json() == {"code": "NOT_EVERYTIME", "message": "에브리타임 시간표 화면 캡처만 읽을 수 있어요."}


def test_지난_학기_캡처는_미리보기에서_400(client, model, jisu, seeded):
    # 확정 요청엔 학기가 안 와서 오늘 학기로 저장된다. 지난 학기 수업이 이번 학기를 막지 않게 거른다.
    model.answer = {**AI_ANSWER, "year": 2023, "semester": "2"}
    before = _snapshot(seeded, jisu.id)
    res = _preview(client, draw(IMAGE_BLOCKS))
    assert res.status_code == 400
    assert res.json() == {
        "code": "CAPTURE_PAST_TERM",
        "message": "2023년 2학기 시간표예요. 이번 학기 시간표를 캡처해 주세요.",
    }
    assert _snapshot(seeded, jisu.id) == before


@pytest.mark.parametrize(
    ("year", "semester"),
    [(2027, "1"), (None, None)],  # 다음 학기를 미리 · 학기를 못 읽음
)
def test_지난_학기가_아니면_미리보기를_돌려준다(client, model, jisu, year, semester):
    model.answer = {**AI_ANSWER, "year": year, "semester": semester}
    res = _preview(client, draw(IMAGE_BLOCKS))
    assert res.status_code == 200
    assert len(res.json()["classes"]) == 4


@pytest.mark.parametrize("answer", [None, {"is_everytime": True, "classes": "깨짐"}])
def test_AI가_실패하면_503_다시_하기(client, model, jisu, answer):
    model.answer = answer
    res = _preview(client, draw(IMAGE_BLOCKS))
    assert res.status_code == 503
    assert res.json() == {"code": "CAPTURE_READ_FAILED", "message": "시간표를 잠시 못 읽었어요. 잠시 후 다시 해 주세요."}


@pytest.mark.parametrize("mime", ["application/json", "image/gif", "text/plain"])
def test_이미지_형식이_아니면_400(client, model, jisu, mime):
    res = _preview(client, b"abc", mime)
    assert res.status_code == 400
    assert res.json()["code"] == "IMAGE_INVALID"
    assert model.calls == []


def test_빈_본문이면_400(client, model, jisu):
    assert _preview(client, b"").json()["code"] == "IMAGE_INVALID"


def test_jpg라고_보내도_jpeg로_받는다(client, model, jisu):
    assert _preview(client, draw(IMAGE_BLOCKS), "image/jpg").status_code == 200


def test_5MB를_넘으면_400(client, model, jisu):
    res = _preview(client, b"0" * (capture.MAX_BYTES + 1))
    assert res.status_code == 400
    assert res.json() == {"code": "IMAGE_TOO_LARGE", "message": "5MB 이하 캡처로 올려 주세요."}
    assert model.calls == []


def test_미리보기는_로그인_안_하면_401(client, model, seeded):
    assert _preview(client, draw(IMAGE_BLOCKS)).status_code == 401


# ── 확정 API ─────────────────────────────────────────────────────────

SAVE = {
    "classes": [
        {"title": "알고리즘", "weekday": 0, "start_min": 630, "end_min": 705},
        {"title": "알고리즘", "weekday": 0, "start_min": 720, "end_min": 795},
        {"title": "모바일응용", "weekday": 3, "start_min": 630, "end_min": 795},
    ],
    "year": 2026,
    "semester": "2",
}


def _add_manual(session: Session, user_id: int) -> None:
    session.add(
        ScheduleItem(
            user_id=user_id,
            group_id=900,
            source=ScheduleSource.MANUAL,
            kind=ScheduleKind.PARTTIME,
            title="카페 알바",
            recurrence=Recurrence.WEEKLY,
            weekday=5,
            start_min=600,
            end_min=720,
        )
    )
    session.commit()


def test_확정하면_수업이_들어가고_응답은_링크_연결과_같다(client, jisu, seeded):
    res = client.post(f"{API}/capture", json=SAVE)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "everytime"
    assert body["connected"] is True and body["status"] == "ok"
    assert body["account"] == "시간표 캡처"
    assert body["imported_count"] == 2  # 과목 수
    assert body["term"] == "2026년 2학기"
    assert body["term_state"] == "current"

    rows = _everytime_rows(seeded, jisu.id)
    assert [(r.title, r.weekday, r.start_min, r.end_min) for r in rows] == [
        ("알고리즘", 0, 630, 705),
        ("알고리즘", 0, 720, 795),
        ("모바일응용", 3, 630, 795),
    ]
    assert all(r.kind == ScheduleKind.CLASS and r.recurrence == Recurrence.WEEKLY for r in rows)
    assert rows[0].group_id == rows[1].group_id != rows[2].group_id  # 과목 하나 = 묶음 하나
    assert service.get_link(seeded, jisu.id).external_ref == service.CAPTURE_REF


def test_다시_확정하면_에브리타임_수업만_바뀐다(client, jisu, seeded):
    _add_manual(seeded, jisu.id)
    client.post(f"{API}/capture", json=SAVE)
    again = {"classes": [{"title": "캡스톤", "weekday": 4, "start_min": 600, "end_min": 780}], "year": 2026, "semester": "2"}
    assert client.post(f"{API}/capture", json=again).status_code == 200
    assert [(r.title, r.weekday) for r in _everytime_rows(seeded, jisu.id)] == [("캡스톤", 4)]
    seeded.expire_all()
    manual = seeded.exec(
        select(ScheduleItem).where(ScheduleItem.user_id == jisu.id, ScheduleItem.source == ScheduleSource.MANUAL)
    ).all()
    assert [m.title for m in manual] == ["카페 알바"]


def test_지난_학기_캡처는_넣고_past(client, jisu):
    body = client.post(f"{API}/capture", json={**SAVE, "year": 2024, "semester": "2"}).json()
    assert body["term"] == "2024년 2학기"
    assert body["term_state"] == "past"


def test_학기가_없으면_오늘이_속한_학기(client, jisu):
    body = client.post(f"{API}/capture", json={"classes": SAVE["classes"]}).json()
    assert body["term"] == "2026년 2학기"
    assert body["term_state"] == "current"


def test_방학에_학기_없이_넣으면_학기_모름(client, jisu, seeded):
    demo_clock.set_clock(seeded, datetime(2026, 8, 1, 9, 0, tzinfo=KST))
    seeded.commit()
    body = client.post(f"{API}/capture", json={"classes": SAVE["classes"]}).json()
    assert body["term"] is None and body["term_state"] is None


def test_캡처_뒤에_링크로_넣으면_링크로_바뀐다(client, jisu, seeded, monkeypatch):
    from app.integration import everytime
    from tests.test_everytime_api import XML

    monkeypatch.setattr(everytime, "fetch_xml", lambda share: XML)
    monkeypatch.setattr(everytime, "configured", lambda: True)
    client.post(f"{API}/capture", json=SAVE)
    body = client.post(API, json={"url": "https://everytime.kr/@AbCd1234"}).json()
    assert body["account"] == "everytime.kr/@AbCd1234"
    assert service.get_link(seeded, jisu.id).external_ref == "AbCd1234"


@pytest.mark.parametrize(
    "classes",
    [
        [],
        [{"title": "  ", "weekday": 0, "start_min": 600, "end_min": 675}],
        [{"title": "거꾸로", "weekday": 0, "start_min": 675, "end_min": 600}],
        [{"title": "요일", "weekday": 7, "start_min": 600, "end_min": 675}],
        [{"title": "하루 넘음", "weekday": 0, "start_min": 600, "end_min": 1445}],
    ],
)
def test_확정_입력이_틀리면_400_그리고_아무것도_안_바뀐다(client, jisu, seeded, classes):
    before = _snapshot(seeded, jisu.id)
    res = client.post(f"{API}/capture", json={"classes": classes})
    assert res.status_code == 400
    assert res.json()["code"] == "INVALID_INPUT"
    assert _snapshot(seeded, jisu.id) == before


def test_확정은_로그인_안_하면_401(client, seeded):
    assert client.post(f"{API}/capture", json=SAVE).status_code == 401
