"""에브리타임 시간표 캡처를 읽는 곳. 레인 B, #66.

캡처 한 장 → `Timetable`. 무엇을 어떻게 넣을지는 timetable.py가 정한다(링크와 같다).
여기서는 저장하지 않는다 — 읽은 결과는 사람이 확인·수정한 뒤에만 들어간다.

**에브리타임 시간표만 받는다.** 직접 입력·구글 캘린더가 따로 있어서, 아무 표나
읽어 주면 이 기능의 의미가 흐려진다. 모델이 에브리타임 화면인지 같이 답한다.

모델 응답은 믿지 않고 여기서 다시 거른다: 요일 이름 → 0=월, "HH:MM" → 분,
5분 단위로 맞춤, 시작 < 끝, 하루 안. 어긋난 칸은 버리고 나머지만 돌려준다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.integration import capture_grid
from app.integration.timetable import TITLE_MAX, ClassTime, Course, Timetable
from app.shared import llm

MIME_TYPES = ("image/png", "image/jpeg", "image/webp")
MAX_BYTES = 5 * 1024 * 1024
MAX_CLASSES = 50
_UNIT_MIN = 5

_DAYS = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
_HHMM = re.compile(r"^\s*(\d{1,2})\s*:\s*(\d{2})\s*$")

PROMPT = """이 이미지가 에브리타임 앱의 시간표 화면 캡처인지 판단하고, 맞으면 수업을 모두 옮겨 적어라.

에브리타임 시간표 화면의 모양:
- 위쪽에 "2024년 2학기" 같은 학기 글씨가 있고 그 아래 시간표 이름(예: 시간표, 기본시간표)이 크게 있다.
- 표의 첫 행은 요일(월 화 수 목 금, 토·일이 있을 수 있음), 왼쪽 첫 열은 시각 숫자다.
- 시각 숫자는 12시간제다. 9 10 11 12 다음의 1 2 3 4 5 6 7 8은 오후(13시~20시)다.
- 시각 숫자는 그 시각 행의 위쪽 선에 붙어 있고, 모든 시각 행의 높이는 같다.
- 수업은 색칠된 칸이다. 칸 안에 과목명(굵은 글씨, 칸이 좁아 여러 줄로 끊길 수 있음), 교수, 강의실이 차례로 있다.
  칸이 좁으면 과목명이 단어 중간에서도 글자 단위로 끊긴다. 끊긴 줄은 이어 붙이되 원래 과목명의
  띄어쓰기는 살린다. 예: "확률과 / 통계" → "확률과 통계", "선형대 / 수학 1" → "선형대수학 1",
  "Data Sc / ience" → "Data Science". 교수·강의실은 적지 않는다.
- 칸의 위끝이 시작 시각, 아래끝이 끝 시각이다. 시각 행 높이에 비례해 분 단위까지 계산한다.
  수업은 보통 정각이나 30분에 시작하고 75분, 150분, 165분처럼 이어진다.
- 같은 과목이 여러 칸이면 칸마다 하나씩 적는다.
- 표 아래에 시각 없이 과목명만 있는 줄(온라인 강의)은 적지 않는다.
- 화면 아래 시트에 칸이 가려져 끝이 안 보이면, 보이는 아래끝을 끝 시각으로 한다.

에브리타임 시간표가 아니면(다른 앱, 직접 그린 표, 사진 등) is_everytime을 false로 하고 classes는 비운다.

JSON 객체 하나만 답한다:
{"is_everytime": true, "year": 2024, "semester": "2",
 "classes": [{"title": "알고리즘", "day": "월", "start": "10:30", "end": "11:45"}]}
- year·semester는 위쪽 학기 글씨에서. semester는 "1", "2" 또는 그 밖의 글자(예: "여름학기"). 안 보이면 null.
- day는 월 화 수 목 금 토 일 중 하나, start·end는 24시간제 "HH:MM"."""


class CaptureError(Exception):
    """캡처 읽기 실패."""


class ReadFailed(CaptureError):
    """모델이 꺼졌거나 실패했거나 답이 깨졌다. 잠시 후 다시 하면 된다."""


class NotEverytime(CaptureError):
    """에브리타임 시간표 화면이 아니다."""


@dataclass(frozen=True)
class CapturedClass:
    title: str
    weekday: int
    start_min: int
    end_min: int


@dataclass(frozen=True)
class Capture:
    year: int | None
    semester: str | None
    classes: tuple[CapturedClass, ...]

    def timetable(self) -> Timetable:
        return to_timetable(self.year, self.semester, self.classes)


def _minutes(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    match = _HHMM.match(value)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 24 or minute > 59:
        return None
    total = hour * 60 + minute
    # 5분 단위로 맞춘다(에브리타임 XML도 5분 단위). 반올림.
    return round(total / _UNIT_MIN) * _UNIT_MIN


def _clean_title(value: object) -> str:
    title = " ".join(str(value or "").split())[:TITLE_MAX]
    return title or "수업"


def _year(value: object) -> int | None:
    try:
        year = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return year if 2000 <= year <= 2100 else None


def _semester(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in ("1", "2"):
        return text
    if text.startswith(("1학기", "2학기")):
        return text[0]
    return text[:10] or None


def parse_answer(answer: dict) -> Capture:
    """모델 답 → Capture. 에브리타임이 아니면 NotEverytime, 모양이 틀리면 ReadFailed."""
    if answer.get("is_everytime") is not True:
        raise NotEverytime("not everytime")
    rows = answer.get("classes")
    if not isinstance(rows, list):
        raise ReadFailed("classes")

    classes: list[CapturedClass] = []
    seen: set[tuple[int, int, int]] = set()
    for row in rows[:MAX_CLASSES]:
        if not isinstance(row, dict):
            continue
        weekday = _DAYS.get(str(row.get("day", "")).strip()[:1])
        start = _minutes(row.get("start"))
        end = _minutes(row.get("end"))
        if weekday is None or start is None or end is None:
            continue
        if not (0 <= start < end <= 24 * 60):
            continue
        key = (weekday, start, end)
        if key in seen:  # 같은 칸을 두 번 읽음
            continue
        seen.add(key)
        classes.append(CapturedClass(_clean_title(row.get("title")), weekday, start, end))

    classes.sort(key=lambda c: (c.weekday, c.start_min))
    return Capture(_year(answer.get("year")), _semester(answer.get("semester")), tuple(classes))


def to_timetable(
    year: int | None, semester: str | None, classes: tuple[CapturedClass, ...] | list[CapturedClass]
) -> Timetable:
    """같은 과목명끼리 묶어 Timetable로. 과목 하나 = 묶음 하나(링크와 같다)."""
    grouped: dict[str, list[ClassTime]] = {}
    for c in classes:
        grouped.setdefault(c.title, []).append(ClassTime(c.weekday, c.start_min, c.end_min))
    courses = tuple(Course(title, tuple(times)) for title, times in grouped.items())
    return Timetable(year=year, semester=semester, courses=courses)


def _key(title: str) -> str:
    return "".join(title.split()).lower()


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def merge(ai: Capture, grid: capture_grid.Grid | None) -> Capture:
    """모델이 읽은 수업이 기본이고, 격자는 그 시각만 다듬는다.

    **격자 때문에 수업이 빠지거나 생기거나 이상해지면 안 된다.** 그래서
    - 결과의 수업 개수·과목명·요일은 언제나 모델 것이다. 격자만 찾은 칸은 넣지 않는다.
    - 같은 요일에서 모델 칸과 격자 칸이 서로 가장 많이 겹치는 짝(1:1)일 때만 시작·끝을
      격자 값으로 바꾼다. 같은 색 칸 두 개가 붙어 격자가 하나로 본 경우처럼 애매하면
      모델 시각을 그대로 둔다. 같은 과목을 쪼개 읽은 칸은 하나로 합친다.
    - 격자를 못 찾았거나 하나도 안 맞으면 모델 답 그대로.

    격자는 "첫 시각선부터 몇 분"만 안다. 첫 시각이 몇 시인지는 모델 칸과 가장 많이
    겹치는 정시로 정한다(보통 9시).
    """
    if grid is None or not grid.blocks or not ai.classes:
        return ai

    def score(first_hour: int) -> float:
        base = first_hour * 60
        return sum(
            _overlap(base + b.start_off, base + b.end_off, c.start_min, c.end_min)
            for b in grid.blocks
            for c in ai.classes
            if c.weekday == b.weekday
        )

    first_hour = max(range(13), key=lambda h: (score(h), h == 9))
    if score(first_hour) == 0:
        return ai  # 모델과 격자가 하나도 안 맞으면 격자를 믿지 않는다
    base = first_hour * 60

    spans: list[tuple[int, int, int]] = []  # (요일, 시작, 끝) 5분 단위
    for b in grid.blocks:
        s = round((base + b.start_off) / _UNIT_MIN) * _UNIT_MIN
        e = round((base + b.end_off) / _UNIT_MIN) * _UNIT_MIN
        if 0 <= s < e <= 24 * 60:
            spans.append((b.weekday, s, e))

    def touching_spans(c: CapturedClass) -> list[int]:
        return [i for i, (w, s, e) in enumerate(spans) if w == c.weekday and _overlap(s, e, c.start_min, c.end_min)]

    def touching_classes(i: int) -> list[CapturedClass]:
        w, s, e = spans[i]
        return [c for c in ai.classes if c.weekday == w and _overlap(s, e, c.start_min, c.end_min)]

    def overlap_with(i: int, c: CapturedClass) -> float:
        _, s, e = spans[i]
        return _overlap(s, e, c.start_min, c.end_min)

    def best_span(c: CapturedClass) -> int | None:
        """가장 많이 겹치는 격자 칸. 똑같이 겹치는 칸이 둘이면 None(애매)."""
        ranked = sorted(touching_spans(c), key=lambda i: -overlap_with(i, c))
        if not ranked or (len(ranked) > 1 and overlap_with(ranked[0], c) == overlap_with(ranked[1], c)):
            return None
        return ranked[0]

    def best_class(i: int) -> CapturedClass | None:
        ranked = sorted(touching_classes(i), key=lambda c: -overlap_with(i, c))
        if not ranked or (len(ranked) > 1 and overlap_with(i, ranked[0]) == overlap_with(i, ranked[1])):
            return None
        return ranked[0]

    classes: list[CapturedClass] = []
    merged: set[int] = set()  # 격자 칸 하나로 합친 칸(같은 과목을 쪼개 읽은 경우)
    for c in ai.classes:
        hits = touching_spans(c)
        if len(hits) == 1:
            others = touching_classes(hits[0])
            if (
                len(others) > 1
                # 모델이 칸 하나를 같은 과목명으로 쪼개 읽었다(11/16 반전 캡처에서 봄).
                # 쪼갠 칸들이 모두 이 격자 칸에만 걸쳐 있을 때만 하나로 합친다.
                and len({_key(o.title) for o in others}) == 1
                and all(len(touching_spans(o)) == 1 for o in others)
            ):
                if hits[0] not in merged:
                    merged.add(hits[0])
                    _, s, e = spans[hits[0]]
                    classes.append(CapturedClass(c.title, c.weekday, s, e))
                continue
        # 서로 가장 많이 겹치는 짝(1:1)일 때만 격자 시각을 쓴다. 칸이 조금 어긋나 이웃 칸에
        # 걸쳐도(11/16: 15:00~16:00·16:00~17:00으로 읽은 두 칸) 짝은 하나로 정해진다.
        b = best_span(c)
        crowded = b is not None and any(
            # 이 격자 칸에만 걸친 다른 수업이 있으면 그 칸은 둘이 나눠 쓰는 칸이다(같은 색 칸이
            # 붙어 격자가 하나로 봄). 한쪽에 칸 전체 시각을 주면 둘이 겹친다.
            o is not c and touching_spans(o) == [b]
            for o in touching_classes(b)
        )
        if b is not None and not crowded and best_class(b) is c:
            _, s, e = spans[b]
            classes.append(CapturedClass(c.title, c.weekday, s, e))
        else:
            classes.append(c)

    classes.sort(key=lambda c: (c.weekday, c.start_min))
    return Capture(ai.year, ai.semester, tuple(classes))


def read(image: bytes, mime: str) -> Capture:
    """캡처 한 장을 읽는다. ReadFailed · NotEverytime을 올린다.

    모델에는 원본을 그대로 보낸다. 표 아래를 잘라 보내 봤지만 입력 토큰이 같았고
    (11/16, 1,667 → 1,669), 격자가 칸을 놓치면 그 칸까지 잘려 모델도 못 보게 된다.
    """
    answer = llm.complete_json_image(PROMPT, image, mime=mime)
    if answer is None:
        raise ReadFailed("llm")
    return merge(parse_answer(answer), capture_grid.measure(image))
