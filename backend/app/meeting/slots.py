"""빈칸 찾기 — 후보 시간을 만든다. AI 아님. 순수 계산.

db-설계.md §6의 2번이다. schedule_item(weekly는 기간 안으로 펼쳐서)과
확정된 meeting을 모아 겹치지 않는 30분 격자를 만들고, preference의 가능
시간 범위 밖은 버린다.

이 파일에 LLM이 들어오지 않는 것이 요점이다. 숫자를 정하는 쪽과 그걸 말로
설명하는 쪽을 파일로 가르면, 리허설과 본 시연이 같은 답을 낸다는 보장이
생긴다(backend/README.md의 파일 배치).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.me.models import Preference, ScheduleItem
from app.shared.base import KST

# 회의는 30분 단위다. 후보의 시작도 :00 아니면 :30이다.
GRID_MIN = 30


@dataclass(frozen=True)
class Busy:
    """한 사람이 이미 묶여 있는 한 구간.

    weekly 시간표를 기간 안으로 펼친 결과이거나, 한 번짜리 일정이거나,
    이미 확정된 팀 회의다. 세 갈래를 한 모양으로 만들어 두면 채점기가
    어디서 왔는지 신경 쓰지 않는다.
    """

    user_id: int
    start_at: datetime
    end_at: datetime
    # 에이전트가 말할 때 쓰는 이름. 개인 약속은 "바쁨"이다 —
    # 구글 캘린더에서 온 제목을 팀원에게 보여 주지 않는다.
    label: str

    def overlaps(self, start_at: datetime, end_at: datetime) -> bool:
        return self.start_at < end_at and start_at < self.end_at

    def gap_to(self, start_at: datetime, end_at: datetime) -> timedelta | None:
        """이 일정과 후보 사이의 빈 시간. 겹치면 None.

        앞뒤로 붙어 있으면 이동이 빠듯하다 — 브리프의 "알바 끝나고 바로라
        이동이 빠듯해요"가 이 값으로 판정된다.
        """
        if self.overlaps(start_at, end_at):
            return None
        if self.end_at <= start_at:
            return start_at - self.end_at
        return self.start_at - end_at


def expand_busy(
    items: Sequence[ScheduleItem],
    window_start: datetime,
    window_end: datetime,
) -> list[Busy]:
    """시간표를 조율 기간 안의 실제 구간들로 펼친다.

    weekly 한 행은 기간 안에 여러 번 나타난다. 월요일 9시 수업은 3주짜리
    기간에서 세 구간이 된다. valid_from/valid_to(학기 범위)를 벗어난 주는
    빼고, 그래서 지난 학기 수업이 후보를 막지 않는다.
    """
    busy: list[Busy] = []
    for item in items:
        if item.recurrence == "once":
            if item.start_at is None or item.end_at is None:
                continue
            if item.start_at < window_end and window_start < item.end_at:
                busy.append(
                    Busy(item.user_id, item.start_at, item.end_at, _label(item))
                )
            continue

        if item.weekday is None or item.start_min is None or item.end_min is None:
            continue

        day = window_start.astimezone(KST).date()
        last = window_end.astimezone(KST).date()
        while day <= last:
            if day.weekday() == item.weekday and _in_term(item, day):
                midnight = datetime.combine(day, datetime.min.time(), tzinfo=KST)
                start_at = midnight + timedelta(minutes=item.start_min)
                end_at = midnight + timedelta(minutes=item.end_min)
                if start_at < window_end and window_start < end_at:
                    busy.append(Busy(item.user_id, start_at, end_at, _label(item)))
            day += timedelta(days=1)
    return busy


def group_by_user(busy: Sequence[Busy]) -> dict[int, list[Busy]]:
    """사람별로 묶는다. 채점 전에 한 번만 부른다.

    채점기가 후보마다 팀 전체 일정을 다시 훑지 않게 하려는 것이다. 한 달
    기간에 6명이 시간표를 꽉 채우면 후보 수 × 사람 수 × 일정 수가 수십만
    번이 된다.
    """
    grouped: dict[int, list[Busy]] = {}
    for item in busy:
        grouped.setdefault(item.user_id, []).append(item)
    return grouped


def _in_term(item: ScheduleItem, day: object) -> bool:
    if item.valid_from is not None and day < item.valid_from:  # type: ignore[operator]
        return False
    if item.valid_to is not None and day > item.valid_to:  # type: ignore[operator]
        return False
    return True


def _label(item: ScheduleItem) -> str:
    """제목이 비면 "바쁨"이다. appointment는 일부러 제목을 비워 둔다."""
    return item.title or "바쁨"


def candidate_windows(
    window_start: datetime,
    window_end: datetime,
    duration_min: int,
) -> list[tuple[datetime, datetime]]:
    """기간을 30분 격자로 훑어 길이가 맞는 구간을 모두 낸다.

    시작을 격자에 맞춰 올린다. 팀장이 10:17에 조율을 열어도 후보는 10:30부터
    나온다 — 10:17 회의를 제안하면 사람이 못 읽는다.
    """
    cursor = _ceil_to_grid(window_start)
    length = timedelta(minutes=duration_min)
    out: list[tuple[datetime, datetime]] = []
    while cursor + length <= window_end:
        out.append((cursor, cursor + length))
        cursor += timedelta(minutes=GRID_MIN)
    return out


def _ceil_to_grid(moment: datetime) -> datetime:
    whole = moment.replace(second=0, microsecond=0)
    remainder = whole.minute % GRID_MIN
    if remainder == 0 and whole == moment:
        return whole
    return whole + timedelta(minutes=GRID_MIN - remainder)


def within_day_range(
    start_at: datetime,
    end_at: datetime,
    prefs: Sequence[Preference],
) -> bool:
    """전원의 "보통 몇 시부터 몇 시까지 가능해요?" 안에 드는지.

    이건 선호가 아니라 가능 여부라서 하드 제약이다 — 질문이 "가능해요?"다.
    범위를 비워 둔 사람은 조건이 없다(브리프: 비면 그 조건을 안 쓴다).

    전원 범위의 교집합이 비면 후보가 하나도 안 나오고, 그게 설계의
    no_common 갈래다. 억지로 범위를 넓히지 않는다.

    자정을 넘는 후보는 버린다. 회의를 하루 안에서만 잡는다.
    """
    local_start = start_at.astimezone(KST)
    local_end = end_at.astimezone(KST)
    if local_start.date() != (local_end - timedelta(minutes=1)).date():
        return False

    start_min = local_start.hour * 60 + local_start.minute
    end_min = start_min + int((local_end - local_start).total_seconds() // 60)

    for pref in prefs:
        if pref.day_start_min is not None and start_min < pref.day_start_min:
            return False
        if pref.day_end_min is not None and end_min > pref.day_end_min:
            return False
    return True


def find_candidates(
    window_start: datetime,
    window_end: datetime,
    duration_min: int,
    prefs: Sequence[Preference],
    team_busy: Sequence[Busy],
) -> list[tuple[datetime, datetime]]:
    """후보 전부. 점수는 매기지 않는다 — scorer.py가 한다.

    팀 전체가 묶인 시간(이미 확정된 회의)만 여기서 버린다. 개인 일정과
    겹치는 후보는 남긴다 — 한 사람만 안 되는 시간은 1명 불참안의 재료라서
    버리면 no_common 갈래가 못 돌아간다(db-설계.md §6).
    """
    return [
        (start_at, end_at)
        for start_at, end_at in candidate_windows(
            window_start, window_end, duration_min
        )
        if within_day_range(start_at, end_at, prefs)
        and not any(b.overlaps(start_at, end_at) for b in team_busy)
    ]
