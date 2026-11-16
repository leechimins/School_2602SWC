"""비교 실험이 돌고, 같은 시드면 같은 숫자가 나오는지(tools/benchmark.py)."""

from tools.benchmark import balance, cumulative, earliest, experiment, make_team, majority, run, scored_week, ttak

import random


def test_같은_시드면_같은_결과() -> None:
    a, _ = experiment(3, seed=1, meeting_counts=(2,))
    b, _ = experiment(3, seed=1, meeting_counts=(2,))
    assert a == b
    assert "다수결" in a and "TTAK 잔고" in a


def test_세_방식_모두_회의를_잡는다() -> None:
    rng = random.Random(3)
    teams = [make_team(rng, 3) for _ in range(3)]
    scored = [[scored_week(t, w) for w in range(3)] for t in teams]
    for choose, ledger in ((earliest, None), (majority, None), (ttak(1.0, 4), balance), (ttak(0.25, 4), cumulative)):
        r = run(teams, scored, 3, choose, ledger)
        assert r.max_burden and all(1 <= x <= 5 for x in r.max_burden)
        assert len(r.spread) == 3
