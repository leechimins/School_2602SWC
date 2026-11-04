"""채점 — 사람별 불편 점수와 후보 순서. AI 아님. 순수 계산.

db-설계.md §6의 3번이다. 점수는 계산이 정하고 에이전트는 그걸 말로
설명할 뿐이다. 그래서 리허설과 본 시연이 같은 답을 낸다.

점수는 1~5다. 화면 용어와 1:1이다(브리프 "같은 말 쓰기"):
  1       괜찮음
  2~3     조금
  4~5     많이
본인에게만 숫자로 보이고, 남에게는 저 세 단어로만 나간다.

**지금 쓰는 재료는 셋이다** — 온보딩 질문 1(가능 시간), 질문 3(선호 시간대),
그리고 시간표. 질문 4(피하고 싶은 시간)는 자유 입력이라 계산으로 쓸 수 없고,
LLM이 붙으면 reason을 다듬는 데 쓰인다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.me.models import Preference
from app.meeting.slots import Busy
from app.shared.base import KST
from app.shared.enums import Daypart

# 여섯 시간대의 경계. 브리프가 이름만 정하고 몇 시부터인지는 안 적었다 —
# 여기가 그 선택이고, 화면에서 설명을 쓸 때 같은 값을 써야 한다.
DAYPART_RANGES: dict[Daypart, tuple[int, int]] = {
    Daypart.MORNING: (6 * 60, 9 * 60),
    Daypart.FORENOON: (9 * 60, 12 * 60),
    Daypart.LUNCH: (12 * 60, 14 * 60),
    Daypart.AFTERNOON: (14 * 60, 18 * 60),
    Daypart.EVENING: (18 * 60, 21 * 60),
    Daypart.NIGHT: (21 * 60, 24 * 60),
}

# 앞뒤 일정과 이 시간보다 가까우면 이동이 빠듯하다고 본다.
TIGHT_GAP = timedelta(minutes=30)

# 겹치는 일정이 있으면 이 점수. available=False와 함께 간다.
BLOCKED_SCORE = 5
# 붙어 있을 때 올리는 폭. 1 + 2 = 3이라 "조금"에 들어간다 —
# 브리프 예시의 "수업 바로 뒤라 조금 빠듯하지만 괜찮아요"가 이 자리다.
TIGHT_PENALTY = 2
# 고른 시간대 밖일 때 올리는 폭.
OFF_DAYPART_PENALTY = 1


@dataclass(frozen=True)
class Cost:
    """한 사람이 한 후보에 대해 느끼는 불편."""

    user_id: int
    score: int
    available: bool
    reason: str


def with_particle(word: str) -> str:
    """뒤에 "와" 또는 "과"를 붙인다. 받침이 있으면 "과", 없으면 "와".

    에이전트가 이 문장을 그대로 말하므로 조사가 틀리면 바로 보인다 —
    "알바과 겹칩니다"는 "알바와 겹칩니다"여야 한다.

    한글 음절의 받침은 (코드포인트 - 0xAC00) % 28로 나온다. 0이면 받침이
    없다. 한글이 아닌 글자(영문 과목 코드 등)로 끝나면 "와"를 쓴다 —
    영문 이름의 받침을 추측하면 더 틀린다.
    """
    code = ord(word[-1])
    if 0xAC00 <= code <= 0xD7A3 and (code - 0xAC00) % 28 != 0:
        return f"{word}과"
    return f"{word}와"


def score_for(
    start_at: datetime,
    end_at: datetime,
    user_id: int,
    pref: Preference | None,
    mine: Sequence[Busy],
) -> Cost:
    """한 사람 한 후보. 1에서 시작해 걸리는 것마다 올린다.

    mine은 **이 사람의** 일정만이다. 거르는 것은 부르는 쪽이 한 번만 한다
    (slots.group_by_user) — 후보마다 팀 전체를 다시 훑으면 기간이 길어질 때
    후보 수 × 사람 수 × 일정 수만큼 늘어난다.
    """
    clash = next((b for b in mine if b.overlaps(start_at, end_at)), None)
    if clash is not None:
        return Cost(
            user_id=user_id,
            score=BLOCKED_SCORE,
            available=False,
            reason=f"{with_particle(clash.label)} 겹칩니다",
        )

    score = 1
    reasons: list[str] = []

    tight = _tightest(start_at, end_at, mine)
    if tight is not None:
        item, comes_before = tight
        score += TIGHT_PENALTY
        when = "바로 뒤라" if comes_before else "바로 전이라"
        reasons.append(f"{item.label} {when} 이동이 빠듯합니다")

    if pref is not None and pref.dayparts and not _in_dayparts(start_at, pref.dayparts):
        score += OFF_DAYPART_PENALTY
        reasons.append("좋다고 한 시간대가 아닙니다")

    return Cost(
        user_id=user_id,
        score=min(score, 5),
        available=True,
        reason=" · ".join(reasons) if reasons else "비어 있는 시간입니다",
    )


def _tightest(
    start_at: datetime, end_at: datetime, mine: Sequence[Busy]
) -> tuple[Busy, bool] | None:
    """앞뒤로 가장 바싹 붙은 일정과, 그게 후보보다 **앞**인지. 없으면 None.

    min(key=...)으로 쓰지 않는다. timedelta(0)이 파이썬에서 거짓이라
    `gap or 기본값` 같은 식을 쓰면 **딱 붙은 일정(간격 0분)이 가장 먼 것으로
    뒤집힌다** — 제일 빠듯한 경우가 제일 한가한 것으로 읽힌다.

    앞인지 뒤인지를 함께 돌려주는 이유: 에이전트가 이 문장을 그대로 말한다.
    뒤에 있는 알바를 "알바 바로 뒤라"라고 하면 틀린 이유를 말하게 된다.
    """
    best: tuple[timedelta, Busy, bool] | None = None
    for item in mine:
        gap = item.gap_to(start_at, end_at)
        if gap is None or gap >= TIGHT_GAP:
            continue
        comes_before = item.end_at <= start_at
        if best is None or gap < best[0]:
            best = (gap, item, comes_before)
    if best is None:
        return None
    return best[1], best[2]


def _in_dayparts(start_at: datetime, dayparts: Sequence[Daypart]) -> bool:
    """후보가 시작하는 시각이 고른 시간대 중 하나에 드는지.

    시작만 본다. 두 시간짜리 회의가 오후에 시작해 저녁에 끝나는 것을
    "저녁이라 싫다"로 치면, 긴 회의가 전부 벌점을 받는다.
    """
    local = start_at.astimezone(KST)
    minute = local.hour * 60 + local.minute
    for part in dayparts:
        bounds = DAYPART_RANGES.get(part)
        if bounds is not None and bounds[0] <= minute < bounds[1]:
            return True
    return False


def score_slot(
    start_at: datetime,
    end_at: datetime,
    member_ids: Sequence[int],
    prefs: Mapping[int, Preference],
    busy_by_user: Mapping[int, Sequence[Busy]],
) -> list[Cost]:
    """후보 하나에 대한 전원의 불편. busy_by_user는 slots.group_by_user의 결과다."""
    return [
        score_for(
            start_at, end_at, user_id, prefs.get(user_id), busy_by_user.get(user_id, ())
        )
        for user_id in member_ids
    ]


def unavailable_count(costs: Sequence[Cost]) -> int:
    """이 후보에 못 오는 사람 수. 0이면 전원 가능하다."""
    return sum(1 for c in costs if not c.available)


def total_cost(costs: Sequence[Cost]) -> float:
    """candidate_slot.total_cost에 들어가는 값. 팀 전체 불편의 단순 합이다.

    가중을 섞지 않는다 — 저장된 값은 "사람들이 실제로 느끼는 합"이어야
    시연에서 열어 보여 줄 수 있다. 양보 차등은 아래 순서 정하기에서만 쓴다.
    """
    return float(sum(c.score for c in costs))


# 누적 양보가 높은 사람의 불편을 더 무겁게 센다. 0 → 1.0, 4 이상 → 2.0.
# 숫자는 고른 값이고 조정할 수 있다. 저장되는 score는 건드리지 않고
# **순서만** 바꾼다 — 사람이 느끼는 불편을 시스템이 고쳐 쓰면 안 된다.
YIELD_WEIGHT_STEP = 0.25
YIELD_WEIGHT_CAP = 4


def yield_weighted_cost(costs: Sequence[Cost], yield_totals: dict[int, int]) -> float:
    """후보를 고를 때 쓰는 값. 낮은 쪽이 먼저다.

    브리프: "현우는 지난 두 번의 회의에서 많이 맞춰 줬어요. 이번엔 현우
    쪽을 먼저 챙겨…" — 그 판단이 이 한 줄이다.
    """
    total = 0.0
    for cost in costs:
        earned = min(yield_totals.get(cost.user_id, 0), YIELD_WEIGHT_CAP)
        total += cost.score * (1 + YIELD_WEIGHT_STEP * earned)
    return total


def pick_order(
    scored: Sequence[tuple[tuple[datetime, datetime], list[Cost]]],
    yield_totals: dict[int, int],
) -> list[tuple[tuple[datetime, datetime], list[Cost]]]:
    """후보를 제안할 순서로 늘어놓는다.

    1. 전원 가능한 후보가 먼저다. 한 명이라도 안 되는 시간은 1명 불참안
       재료일 뿐이라 뒤로 보낸다.
    2. 그다음 양보 가중 합이 낮은 순.
    3. 같으면 이른 시각 순 — 같은 점수면 빨리 끝나는 쪽이 낫고,
       순서가 매번 같아야 리허설과 본 시연이 일치한다.
    """
    return sorted(
        scored,
        key=lambda pair: (
            unavailable_count(pair[1]),
            yield_weighted_cost(pair[1], yield_totals),
            pair[0][0],
        ),
    )
