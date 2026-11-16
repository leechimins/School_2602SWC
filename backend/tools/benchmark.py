"""회의 시간 고르는 방식 비교 실험. 서비스 동작은 건드리지 않는다.

    python -m tools.benchmark                       # 결과를 docs/benchmark.md로
    python -m tools.benchmark --teams 50 --stdout   # 빨리 화면으로만

가상 팀(4명)을 만들어 한 학기 동안 매주 회의를 하나씩 잡는다. 후보 만들기와
불편 점수는 **서비스와 같은 함수**(slots.find_candidates, scorer.score_slot)를
그대로 쓴다. 다른 것은 "어느 후보를 고르나"뿐이다.

  - 가장 이른 공통 시간: 전원 가능한 첫 시간
  - 다수결: 각자 가장 편한 시간에 투표, 최다 득표(같으면 이른 시간)
  - TTAK 누적(지금까지 방식): 양보를 쌓기만 한다
  - TTAK 잔고(새 방식): 참으면 쌓이고 배려를 받으면 쓴다

TTAK 둘은 조율 루프와 같은 순서로 고른다(agent_loop.run_rounds를 DB 없이
옮긴 것): 각자 가장 편한 시간을 어필 → 양보 가중 합이 가장 낮은 것 → 누가
4점 이상이면 거절, 최대 3라운드 → 실패하면 거절을 가장 적게 꺾는 시간으로 조정.

같은 시드면 같은 숫자가 나온다.
"""

from __future__ import annotations

import argparse
import random
import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from app.me.models import Preference, ScheduleItem
from app.meeting.agent_loop import MAX_ROUNDS, REJECT_AT
from app.meeting.scorer import (
    Cost,
    best_for,
    rejecting_count,
    score_slot,
    unavailable_count,
    YIELD_WEIGHT_CAP,
    YIELD_WEIGHT_STEP,
    yield_points,
    yield_weighted_cost,
)
from app.meeting.slots import expand_busy, find_candidates, group_by_user
from app.shared.base import KST
from app.shared.enums import Daypart, Recurrence, ScheduleKind, ScheduleSource

Slot = tuple[datetime, datetime]
Scored = list[tuple[Slot, list[Cost]]]

MEMBERS = 4
DURATION_MIN = 90
FIRST_MONDAY = date(2026, 9, 7)  # 2학기 첫 주


# ── 가상 팀 ─────────────────────────────────────────────────────────


@dataclass
class Team:
    prefs: dict[int, Preference]
    weekly: list[ScheduleItem]  # 매주 같은 수업·알바
    weeks: list[list[ScheduleItem]]  # 주마다 다른 한 번짜리 약속


def _weekly(rng: random.Random, uid: int) -> list[ScheduleItem]:
    items: list[ScheduleItem] = []
    for _ in range(rng.randint(4, 8)):
        start = rng.choice([9 * 60, 10 * 60 + 30, 12 * 60, 13 * 60 + 30, 15 * 60, 16 * 60 + 30])
        items.append(
            ScheduleItem(
                user_id=uid, source=ScheduleSource.EVERYTIME, kind=ScheduleKind.CLASS,
                title="수업", recurrence=Recurrence.WEEKLY,
                weekday=rng.randint(0, 4), start_min=start, end_min=start + rng.choice([75, 90]),
            )
        )
    for _ in range(rng.randint(0, 2)):
        start = rng.choice([17 * 60, 18 * 60])
        items.append(
            ScheduleItem(
                user_id=uid, source=ScheduleSource.MANUAL, kind=ScheduleKind.PARTTIME,
                title="알바", recurrence=Recurrence.WEEKLY,
                weekday=rng.randint(0, 6), start_min=start, end_min=start + rng.choice([180, 240]),
            )
        )
    return items


def _pref(rng: random.Random, uid: int) -> Preference:
    parts = [Daypart.FORENOON, Daypart.LUNCH, Daypart.AFTERNOON, Daypart.EVENING]
    pref = Preference(
        user_id=uid,
        day_start_min=rng.choice([9, 10, 11]) * 60,
        day_end_min=rng.choice([20, 21, 22]) * 60,
        dayparts=rng.sample(parts, rng.randint(1, 2)),
    )
    if rng.random() < 0.5:
        pref.avoid_weekdays = [rng.randint(0, 4)]
        pref.avoid_start_min, pref.avoid_end_min = rng.choice([(9 * 60, 12 * 60), (18 * 60, 22 * 60)])
        pref.avoid_polished = "피하고 싶은 시간입니다"
    return pref


def make_team(rng: random.Random, weeks: int) -> Team:
    uids = list(range(1, MEMBERS + 1))
    prefs = {uid: _pref(rng, uid) for uid in uids}
    weekly = [item for uid in uids for item in _weekly(rng, uid)]
    per_week: list[list[ScheduleItem]] = []
    for w in range(weeks):
        monday = FIRST_MONDAY + timedelta(weeks=w)
        items = []
        for uid in uids:
            for _ in range(rng.randint(0, 2)):  # 그 주에만 있는 약속
                day = monday + timedelta(days=rng.randint(0, 4))
                start = datetime.combine(day, datetime.min.time(), tzinfo=KST) + timedelta(
                    minutes=rng.choice(range(10 * 60, 20 * 60, 30))
                )
                items.append(
                    ScheduleItem(
                        user_id=uid, source=ScheduleSource.GOOGLE, kind=ScheduleKind.APPOINTMENT,
                        recurrence=Recurrence.ONCE, start_at=start,
                        end_at=start + timedelta(minutes=rng.choice([60, 90, 120])),
                    )
                )
        per_week.append(items)
    return Team(prefs=prefs, weekly=weekly, weeks=per_week)


def scored_week(team: Team, week: int) -> Scored:
    """그 주(월~금)의 후보와 사람별 불편. 서비스의 start_scheduling과 같은 길이다."""
    monday = FIRST_MONDAY + timedelta(weeks=week)
    start = datetime.combine(monday, datetime.min.time(), tzinfo=KST)
    end = start + timedelta(days=5)
    uids = sorted(team.prefs)
    busy = group_by_user(expand_busy(team.weekly + team.weeks[week], start, end))
    found = find_candidates(start, end, DURATION_MIN, list(team.prefs.values()), [])
    return [(slot, score_slot(slot[0], slot[1], uids, team.prefs, busy)) for slot in found]


# ── 고르는 방식 ──────────────────────────────────────────────────────

Chooser = Callable[[Scored, Mapping[int, float]], tuple[Slot, list[Cost]] | None]


def _everyone(scored: Scored) -> Scored:
    return [p for p in scored if unavailable_count(p[1]) == 0]


def earliest(scored: Scored, _: Mapping[int, float]) -> tuple[Slot, list[Cost]] | None:
    pool = _everyone(scored) or scored
    return min(pool, key=lambda p: (unavailable_count(p[1]), p[0][0]), default=None)


def majority(scored: Scored, _: Mapping[int, float]) -> tuple[Slot, list[Cost]] | None:
    pool = _everyone(scored)
    if not pool:
        return earliest(scored, {})
    votes: dict[Slot, int] = {}
    for uid in {c.user_id for c in pool[0][1]}:
        slot = best_for(uid, pool)
        if slot is not None:
            votes[slot] = votes.get(slot, 0) + 1
    return min(pool, key=lambda p: (-votes.get(p[0], 0), p[0][0]))


def ttak(step: float, cap: float) -> Chooser:
    """조율 루프와 같은 순서. 거절 → 다음 라운드, 3번 넘으면 조정."""

    def weighted(pair: tuple[Slot, list[Cost]], yields: Mapping[int, float]) -> float:
        return yield_weighted_cost(pair[1], yields, step, cap)

    def choose(scored: Scored, yields: Mapping[int, float]) -> tuple[Slot, list[Cost]] | None:
        남은것 = _everyone(scored)
        uids = sorted({c.user_id for c in scored[0][1]}) if scored else []
        for _ in range(MAX_ROUNDS):
            if not 남은것:
                break
            appeals = [s for uid in uids if (s := best_for(uid, 남은것)) is not None]
            어필된것 = [p for p in 남은것 if p[0] in appeals] or 남은것
            pick = min(어필된것, key=lambda p: (weighted(p, yields), -appeals.count(p[0]), p[0][0]))
            if rejecting_count(pick[1], REJECT_AT) == 0:
                return pick
            남은것 = [p for p in 남은것 if p[0] != pick[0]]
        # 조정: 못 오는 사람 → 꺾을 사람 → 가중 합 → 이른 시각(scorer.pick_order와 같은 순서)
        return min(
            scored,
            key=lambda p: (unavailable_count(p[1]), rejecting_count(p[1], REJECT_AT), weighted(p, yields), p[0][0]),
            default=None,
        )

    return choose


# ── 양보 장부 ────────────────────────────────────────────────────────


def cumulative(yields: dict[int, float], attended: Sequence[Cost]) -> None:
    for c in attended:
        yields[c.user_id] = yields.get(c.user_id, 0) + yield_points(c.score, True)


def balance(yields: dict[int, float], attended: Sequence[Cost]) -> None:
    if not attended:
        return
    points = {c.user_id: yield_points(c.score, True) for c in attended}
    mean = sum(points.values()) / len(points)
    for uid, p in points.items():
        yields[uid] = yields.get(uid, 0.0) + p - mean


# ── 실행과 지표 ──────────────────────────────────────────────────────


@dataclass
class Result:
    max_burden: list[int] = field(default_factory=list)  # 회의마다 가장 불편한 사람
    total: list[int] = field(default_factory=list)  # 회의마다 팀 불편 합
    much: list[int] = field(default_factory=list)  # 회의마다 많이 불편(4+)한 사람 수
    spread: list[float] = field(default_factory=list)  # 팀마다 학기 끝 사람별 누적 불편의 표준편차
    worst_person: list[int] = field(default_factory=list)  # 팀마다 가장 많이 참은 사람의 누적


def run(teams: Sequence[Team], weeks_scored: Sequence[Sequence[Scored]], meetings: int,
        choose: Chooser, ledger: Callable[[dict[int, float], Sequence[Cost]], None] | None) -> Result:
    out = Result()
    for team, weeks in zip(teams, weeks_scored, strict=True):
        yields: dict[int, float] = {}
        burden = {uid: 0 for uid in team.prefs}
        for w in range(meetings):
            pick = choose(list(weeks[w]), yields)
            if pick is None:
                continue
            attended = [c for c in pick[1] if c.available]
            scores = [c.score for c in attended]
            out.max_burden.append(max(scores))
            out.total.append(sum(scores))
            out.much.append(sum(1 for s in scores if s >= REJECT_AT))
            for c in attended:
                burden[c.user_id] += c.score - 1  # 괜찮음(1)은 참은 게 아니다
            if ledger is not None:
                ledger(yields, attended)
        out.spread.append(statistics.pstdev(burden.values()))
        out.worst_person.append(max(burden.values()))
    return out


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def row(name: str, r: Result) -> str:
    return (
        f"| {name} | {_mean(r.max_burden):.2f} | {_mean(r.total):.2f} | {_mean(r.much):.3f} "
        f"| {_mean(r.spread):.2f} | {_mean(r.worst_person):.2f} |"
    )


HEAD = (
    "| 방식 | 최대 불편(회의당) | 팀 불편 합(회의당) | 많이 불편한 사람(회의당) | 학기 끝 불편 편차 ↓ | 가장 많이 참은 사람 누적 |\n"
    "|---|---|---|---|---|---|"
)

STEPS = (0.0, 0.1, 0.25, 0.5, 1.0)
CAPS = (2, 4, 8)


def experiment(n_teams: int, seed: int, meeting_counts: Sequence[int] = (5, 20)) -> str:
    rng = random.Random(seed)
    weeks = max(meeting_counts)
    teams = [make_team(rng, weeks) for _ in range(n_teams)]
    scored = [[scored_week(t, w) for w in range(weeks)] for t in teams]

    lines = [
        "# 회의 시간 고르는 방식 비교",
        "",
        f"`python -m tools.benchmark --teams {n_teams} --seed {seed}` 결과. 가상 팀 {n_teams}개 × {MEMBERS}명, "
        f"주마다 회의 하나({DURATION_MIN}분, 월~금). 불편 점수는 서비스와 같은 함수(1 괜찮음 ~ 5 못 옴).",
        "",
        "- **최대 불편**: 그 회의에서 가장 불편한 참석자의 점수",
        "- **학기 끝 불편 편차**: 사람마다 학기 동안 참은 불편(점수−1)을 더한 뒤 팀 안 표준편차. 작을수록 고르게 나눠 참았다",
        "",
    ]
    summary: dict[int, dict[str, Result]] = {}
    for m in meeting_counts:
        base = {
            "가장 이른 공통 시간": run(teams, scored, m, earliest, None),
            "다수결": run(teams, scored, m, majority, None),
            "TTAK 누적 (0.25, 상한 4)": run(teams, scored, m, ttak(0.25, 4), cumulative),
            f"**TTAK 잔고 ({YIELD_WEIGHT_STEP}, 상한 {YIELD_WEIGHT_CAP}) — 채택**": run(
                teams, scored, m, ttak(YIELD_WEIGHT_STEP, YIELD_WEIGHT_CAP), balance
            ),
        }
        summary[m] = base
        lines += [f"## 회의 {m}번", "", HEAD, *(row(k, v) for k, v in base.items()), ""]
        lines += [f"### 잔고 방식 비율·상한 (회의 {m}번)", "", HEAD]
        for cap in CAPS:
            for step in STEPS:
                if step == 0 and cap != CAPS[0]:
                    continue  # 비율 0이면 상한은 상관없다
                r = run(teams, scored, m, ttak(step, cap), balance)
                lines.append(row(f"비율 {step}, 상한 {cap}", r))
        lines.append("")
    return "\n".join(lines) + "\n", summary  # type: ignore[return-value]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--teams", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--stdout", action="store_true")
    args = ap.parse_args()
    text, _ = experiment(args.teams, args.seed)
    if args.stdout:
        print(text)
        return
    out = Path(__file__).resolve().parents[2] / "docs" / "benchmark.md"
    out.write_text(text, encoding="utf-8")
    print(f"썼습니다: {out}")


if __name__ == "__main__":
    main()
