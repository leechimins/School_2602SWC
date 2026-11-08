"""수업 시간표를 schedule_item으로 넣는 곳. 레인 B.

**어디서 읽었는지 모른다.** 에브리타임 공유 링크(everytime.py)든, 나중에 붙일
시간표 캡처(이미지 → AI)든 `Timetable` 하나로 만들어 넘기면 같은 규칙으로
들어간다. 읽는 방법을 바꿀 때 이 파일은 안 고친다.

- 수업은 schedule_item(source=everytime, kind=class, weekly)이 된다.
- 넣을 때마다 이전 에브리타임 수업을 지우고 새로 넣는다. 직접 입력·구글 행은
  안 건드린다. 직접 입력과 겹쳐도 막지 않는다 — 수업 시간은 에브리타임이 맞다
  (me/schedule.py의 CLASS_CONFLICT와 같은 판단).
- 과목 하나가 묶음 하나다. group_id는 내 묶음 중 가장 큰 번호 + 1부터 —
  시드가 101 같은 고정 번호를 쓰므로 행 id를 쓰지 않는다(me/schedule.py와 같다).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import delete, func
from sqlmodel import Session, select

from app.me.models import ScheduleItem
from app.shared.enums import Recurrence, ScheduleKind, ScheduleSource

TITLE_MAX = 60  # schedule_item.title 길이


@dataclass(frozen=True)
class ClassTime:
    weekday: int  # 0=월 … 6=일
    start_min: int  # 자정부터 분
    end_min: int


@dataclass(frozen=True)
class Course:
    title: str
    times: tuple[ClassTime, ...]


@dataclass(frozen=True)
class Timetable:
    """읽어 온 시간표 한 학기. 학기를 모르면 year·semester가 None이다."""

    year: int | None
    semester: str | None
    courses: tuple[Course, ...]


# 학기 범위. 조율(meeting/slots.py)이 이 범위 밖의 주는 수업을 안 센다 —
# 지난 학기 링크를 넣어도 이번 학기 후보를 막지 않는다.
# 계절학기 등 모르는 값은 범위 없이 넣는다(매주 반복으로 센다).
_TERMS: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
    "1": ((3, 1), (6, 30)),
    "2": ((9, 1), (12, 31)),
}


def term_range(table: Timetable) -> tuple[date | None, date | None]:
    if table.year is None or table.semester not in _TERMS:
        return None, None
    (fm, fd), (tm, td) = _TERMS[table.semester]
    return date(table.year, fm, fd), date(table.year, tm, td)


def term_label(table: Timetable) -> str | None:
    """화면에 띄울 학기. 예: "2026년 2학기". 지난 학기 링크인지 사람이 알아보게 한다."""
    if table.year is None or not table.semester:
        return None
    if table.semester in _TERMS:
        return f"{table.year}년 {table.semester}학기"
    return f"{table.year}년 {table.semester}"


def _clean(course: Course) -> tuple[str, list[ClassTime]]:
    """CHECK 제약에 걸릴 값은 여기서 버린다. 행 하나 때문에 전체가 실패하지 않게."""
    title = " ".join(course.title.split())[:TITLE_MAX] or "수업"
    times: list[ClassTime] = []
    for t in course.times:
        ok = 0 <= t.weekday <= 6 and 0 <= t.start_min < t.end_min <= 24 * 60
        if ok and t not in times:
            times.append(t)
    return title, sorted(times, key=lambda t: (t.weekday, t.start_min))


def class_count(db: Session, user_id: int) -> int:
    """에브리타임에서 들어온 수업 수(과목 단위)."""
    return db.exec(
        select(func.count(func.distinct(ScheduleItem.group_id))).where(
            ScheduleItem.user_id == user_id,
            ScheduleItem.source == ScheduleSource.EVERYTIME,
        )
    ).one()


def remove_classes(db: Session, user_id: int) -> None:
    db.execute(
        delete(ScheduleItem).where(
            ScheduleItem.user_id == user_id,
            ScheduleItem.source == ScheduleSource.EVERYTIME,
        )
    )


def replace_classes(db: Session, user_id: int, table: Timetable) -> int:
    """이전 에브리타임 수업을 지우고 새로 넣는다. 넣은 과목 수. 커밋은 부르는 쪽."""
    remove_classes(db, user_id)
    db.flush()
    next_group = (
        db.exec(
            select(func.max(ScheduleItem.group_id)).where(ScheduleItem.user_id == user_id)
        ).one()
        or 0
    ) + 1
    valid_from, valid_to = term_range(table)

    added = 0
    for course in table.courses:
        title, times = _clean(course)
        if not times:  # 시간 없는 과목(온라인 강의 등)은 막는 시간이 없다
            continue
        for t in times:
            db.add(
                ScheduleItem(
                    user_id=user_id,
                    group_id=next_group,
                    source=ScheduleSource.EVERYTIME,
                    kind=ScheduleKind.CLASS,
                    title=title,
                    recurrence=Recurrence.WEEKLY,
                    weekday=t.weekday,
                    start_min=t.start_min,
                    end_min=t.end_min,
                    valid_from=valid_from,
                    valid_to=valid_to,
                )
            )
        next_group += 1
        added += 1
    return added
