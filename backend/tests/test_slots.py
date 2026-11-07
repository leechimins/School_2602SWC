"""빈칸 찾기와 채점. DB도 서버도 AI도 없이 돈다.

조율에서 숫자를 정하는 곳 전부가 여기 걸린다. 여기가 틀리면 에이전트가
말을 잘해도 틀린 시간을 제안한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.me.models import Preference, ScheduleItem
from app.meeting import scorer
from app.meeting.slots import (
    Busy,
    candidate_windows,
    expand_busy,
    find_candidates,
    group_by_user,
    within_day_range,
)
from app.shared.base import KST
from app.shared.enums import Daypart, Recurrence, ScheduleKind, ScheduleSource

MON = datetime(2026, 11, 9, 0, 0, tzinfo=KST)  # 2026-11-09는 월요일이다


def at(day_offset: int, hour: int, minute: int = 0) -> datetime:
    return MON + timedelta(days=day_offset, hours=hour, minutes=minute)


def a_class(user_id: int, weekday: int, start_h: int, end_h: int, **kw) -> ScheduleItem:
    kw.setdefault("source", ScheduleSource.EVERYTIME)
    kw.setdefault("kind", ScheduleKind.CLASS)
    kw.setdefault("title", "서비스디자인")
    return ScheduleItem(
        user_id=user_id,
        recurrence=Recurrence.WEEKLY,
        weekday=weekday,
        start_min=start_h * 60,
        end_min=end_h * 60,
        **kw,
    )


# ── 격자 ────────────────────────────────────────────────────────────


def test_후보는_30분_격자로_나온다() -> None:
    windows = candidate_windows(at(0, 9), at(0, 11), duration_min=60)
    assert windows == [
        (at(0, 9), at(0, 10)),
        (at(0, 9, 30), at(0, 10, 30)),
        (at(0, 10), at(0, 11)),
    ]


def test_격자에_안_맞는_시작은_올려_붙인다() -> None:
    """팀장이 10:17에 열어도 10:17 회의를 제안하지 않는다."""
    windows = candidate_windows(at(0, 10, 17), at(0, 12), duration_min=60)
    assert windows[0][0] == at(0, 10, 30)


def test_길이가_안_들어가면_후보가_없다() -> None:
    assert candidate_windows(at(0, 9), at(0, 10), duration_min=120) == []


# ── 시간표 펼치기 ────────────────────────────────────────────────────


def test_주간_수업이_기간_안에_여러_번_나타난다() -> None:
    """월 9시 수업은 3주 기간에서 세 구간이 된다."""
    busy = expand_busy([a_class(1, weekday=0, start_h=9, end_h=11)], MON, MON + timedelta(days=21))
    assert len(busy) == 3
    assert [b.start_at for b in busy] == [at(0, 9), at(7, 9), at(14, 9)]


def test_학기_밖의_수업은_안_펼쳐진다() -> None:
    """지난 학기 수업이 후보를 막으면 안 된다."""
    item = a_class(1, weekday=0, start_h=9, end_h=11, valid_to=MON.date() - timedelta(days=1))
    assert expand_busy([item], MON, MON + timedelta(days=21)) == []


def test_일정_이름_대신_분류로_말한다() -> None:
    """일정 이름은 본인에게만 보인다(목업 "이름 (나만 보여요)"). 조율 발언에는 분류만.

    제목이 있어도(편의점 알바) 없어도(구글 약속) 같다. 이름을 넘기면 LLM이 그 근거를
    그대로 다듬어 "편의점 알바와 겹칩니다"가 팀에 나간다.
    """
    def 한칸(kind: ScheduleKind, title: str | None) -> ScheduleItem:
        return ScheduleItem(
            user_id=1, source=ScheduleSource.MANUAL, kind=kind, title=title,
            recurrence=Recurrence.ONCE, start_at=at(0, 14), end_at=at(0, 15),
        )

    window = (MON, MON + timedelta(days=7))
    assert expand_busy([한칸(ScheduleKind.CLASS, "서비스디자인")], *window)[0].label == "수업"
    assert expand_busy([한칸(ScheduleKind.PARTTIME, "편의점 알바")], *window)[0].label == "아르바이트"
    assert expand_busy([한칸(ScheduleKind.APPOINTMENT, None)], *window)[0].label == "일정"


# ── 가능 시간 범위 ──────────────────────────────────────────────────


def test_전원의_가능_시간_안에_들어야_한다() -> None:
    아침형 = Preference(user_id=1, day_start_min=8 * 60, day_end_min=17 * 60)
    저녁형 = Preference(user_id=2, day_start_min=12 * 60, day_end_min=23 * 60)
    prefs = [아침형, 저녁형]

    assert within_day_range(at(0, 13), at(0, 15), prefs) is True
    assert within_day_range(at(0, 9), at(0, 11), prefs) is False  # 저녁형의 아래
    assert within_day_range(at(0, 16), at(0, 18), prefs) is False  # 아침형의 위


def test_범위를_비운_사람은_조건이_없다() -> None:
    """브리프: 네 개를 다 비워도 다음으로 넘어갑니다."""
    prefs = [Preference(user_id=1), Preference(user_id=2, day_start_min=9 * 60)]
    assert within_day_range(at(0, 22), at(0, 23), prefs) is True


def test_자정을_넘는_후보는_버린다() -> None:
    assert within_day_range(at(0, 23), at(1, 1), []) is False


# ── 후보 고르기 ──────────────────────────────────────────────────────


def test_확정된_팀_회의와_겹치는_후보는_버린다() -> None:
    팀회의 = Busy(user_id=0, start_at=at(0, 10), end_at=at(0, 12), label="팀 회의")
    found = find_candidates(at(0, 9), at(0, 13), 60, [], [팀회의])
    assert (at(0, 10), at(0, 11)) not in found
    assert (at(0, 12), at(0, 13)) in found


def test_한_사람만_안_되는_시간은_남긴다(
) -> None:
    """1명 불참안의 재료다. 버리면 no_common 갈래가 못 돌아간다."""
    혼자바쁨 = Busy(user_id=1, start_at=at(0, 10), end_at=at(0, 12), label="알바")
    found = find_candidates(at(0, 9), at(0, 13), 60, [], [])
    assert (at(0, 10), at(0, 11)) in found
    # team_busy에 넣지 않았으므로 남아 있다 — 사람별 판정은 scorer가 한다.
    assert 혼자바쁨.overlaps(at(0, 10), at(0, 11)) is True


# ── 채점 ────────────────────────────────────────────────────────────


def test_겹치면_안_되는_시간이_되고_5점이다() -> None:
    알바 = Busy(user_id=3, start_at=at(0, 18), end_at=at(0, 22), label="아르바이트")
    cost = scorer.score_for(at(0, 19), at(0, 20), 3, None, [알바])
    assert cost.available is False
    assert cost.score == 5
    assert cost.reason == "아르바이트가 있습니다"


def test_비어_있으면_1점_괜찮음이다() -> None:
    cost = scorer.score_for(at(0, 14), at(0, 16), 3, None, [])
    assert cost.score == 1
    assert cost.available is True


def test_바로_뒤에_붙으면_조금_불편해진다() -> None:
    """브리프 예시: "알바 끝나고 바로라 이동이 빠듯해요" → 조금(2~3)."""
    알바 = Busy(user_id=3, start_at=at(0, 10), end_at=at(0, 13), label="알바")
    cost = scorer.score_for(at(0, 13), at(0, 14), 3, None, [알바])
    assert cost.score == 3  # 조금
    assert "빠듯" in cost.reason


def test_30분_넘게_떨어져_있으면_벌점이_없다() -> None:
    알바 = Busy(user_id=3, start_at=at(0, 10), end_at=at(0, 13), label="알바")
    cost = scorer.score_for(at(0, 14), at(0, 15), 3, None, [알바])
    assert cost.score == 1


def test_딱_붙은_일정이_가장_빠듯한_것으로_뽑힌다() -> None:
    """timedelta(0)이 파이썬에서 거짓이라, `gap or 기본값`을 쓰면 간격 0분이
    가장 먼 것으로 뒤집힌다. 제일 빠듯한 경우가 제일 한가한 것으로 읽힌다.
    """
    딱붙음 = Busy(user_id=3, start_at=at(0, 12), end_at=at(0, 14), label="수업")
    조금뒤 = Busy(user_id=3, start_at=at(0, 15, 15), end_at=at(0, 18), label="아르바이트")

    cost = scorer.score_for(at(0, 14), at(0, 15), 3, None, [딱붙음, 조금뒤])
    assert "수업" in cost.reason
    assert "아르바이트" not in cost.reason


def test_뒤에_있는_일정은_바로_전이라고_말한다() -> None:
    """에이전트가 이 문장을 그대로 말한다. 뒤에 있는 알바를 "바로 뒤"라고
    하면 틀린 이유를 말하게 된다.
    """
    뒤에알바 = Busy(user_id=3, start_at=at(0, 15, 10), end_at=at(0, 19), label="아르바이트")
    앞에수업 = Busy(user_id=3, start_at=at(0, 12), end_at=at(0, 13, 50), label="수업")

    뒤 = scorer.score_for(at(0, 14), at(0, 15), 3, None, [뒤에알바])
    assert 뒤.reason == "아르바이트 바로 전이라 이동이 빠듯합니다"

    앞 = scorer.score_for(at(0, 14), at(0, 15), 3, None, [앞에수업])
    assert 앞.reason == "수업 바로 뒤라 이동이 빠듯합니다"


def test_사람별로_묶으면_남의_일정이_안_섞인다() -> None:
    """채점기는 후보마다 팀 전체를 훑지 않는다. 묶는 건 한 번만 한다."""
    내일정 = Busy(user_id=3, start_at=at(0, 10), end_at=at(0, 12), label="내 알바")
    남일정 = Busy(user_id=9, start_at=at(0, 10), end_at=at(0, 12), label="남의 알바")

    grouped = group_by_user([내일정, 남일정])
    assert grouped[3] == [내일정]
    assert grouped[9] == [남일정]

    costs = scorer.score_slot(at(0, 10), at(0, 11), [3, 9], {}, grouped)
    assert all(c.available is False for c in costs)
    assert {c.user_id: c.reason for c in costs}[3] == "내 알바가 있습니다"


def test_못_오는_사람_수를_센다() -> None:
    costs = [
        scorer.Cost(1, 1, True, ""),
        scorer.Cost(2, 5, False, ""),
        scorer.Cost(3, 5, False, ""),
    ]
    assert scorer.unavailable_count(costs) == 2
    assert scorer.unavailable_count([scorer.Cost(1, 1, True, "")]) == 0


def test_고른_시간대_밖이면_한_점_올라간다() -> None:
    오후만 = Preference(user_id=2, dayparts=[Daypart.AFTERNOON])
    안쪽 = scorer.score_for(at(0, 15), at(0, 16), 2, 오후만, [])
    바깥 = scorer.score_for(at(0, 10), at(0, 11), 2, 오후만, [])
    assert 안쪽.score == 1
    assert 바깥.score == 2


def test_시간대는_시작_시각으로_본다() -> None:
    """긴 회의가 다음 시간대로 넘어간다고 벌점을 주지 않는다."""
    오후만 = Preference(user_id=2, dayparts=[Daypart.AFTERNOON])
    cost = scorer.score_for(at(0, 17), at(0, 19), 2, 오후만, [])
    assert cost.score == 1


def test_총합은_단순_합이다() -> None:
    """저장되는 값은 사람들이 실제로 느끼는 합이어야 열어 보여 줄 수 있다."""
    costs = [
        scorer.Cost(1, 1, True, ""),
        scorer.Cost(2, 3, True, ""),
        scorer.Cost(3, 5, False, ""),
    ]
    assert scorer.total_cost(costs) == 9.0


# ── 양보 차등 ───────────────────────────────────────────────────────


def test_누적_양보가_높은_사람의_불편이_더_무겁다() -> None:
    """브리프: "현우는 지난 두 번의 회의에서 많이 맞춰 줬어요"."""
    costs = [scorer.Cost(1, 1, True, ""), scorer.Cost(3, 3, True, "")]
    평등 = scorer.yield_weighted_cost(costs, {})
    현우가_맞춰_왔음 = scorer.yield_weighted_cost(costs, {3: 3})
    assert 현우가_맞춰_왔음 > 평등


def test_양보_차등이_후보_순서를_바꾼다() -> None:
    """총합이 같아도, 많이 맞춰 준 사람이 편한 쪽을 먼저 제안한다."""
    현우가_불편 = ((at(0, 10), at(0, 11)), [scorer.Cost(1, 1, True, ""), scorer.Cost(3, 3, True, "")])
    지수가_불편 = ((at(0, 14), at(0, 15)), [scorer.Cost(1, 3, True, ""), scorer.Cost(3, 1, True, "")])

    # 평등하면 총합이 같으므로 이른 시각이 먼저다.
    평등 = scorer.pick_order([현우가_불편, 지수가_불편], {})
    assert 평등[0] == 현우가_불편

    # 현우가 맞춰 온 기록이 있으면 현우가 편한 쪽이 먼저다.
    차등 = scorer.pick_order([현우가_불편, 지수가_불편], {3: 3})
    assert 차등[0] == 지수가_불편


def test_전원_가능한_후보가_항상_먼저다() -> None:
    한명_불가 = ((at(0, 10), at(0, 11)), [scorer.Cost(1, 1, True, ""), scorer.Cost(3, 5, False, "")])
    전원_가능 = ((at(0, 14), at(0, 15)), [scorer.Cost(1, 3, True, ""), scorer.Cost(3, 3, True, "")])

    order = scorer.pick_order([한명_불가, 전원_가능], {})
    assert order[0] == 전원_가능  # 총합이 더 높아도 먼저다


def test_조사가_받침에_맞게_붙는다() -> None:
    """에이전트가 그대로 말하는 문장이라 조사가 틀리면 바로 보인다."""
    assert scorer.with_subject("수업") == "수업이"          # 받침 있음
    assert scorer.with_subject("아르바이트") == "아르바이트가"  # 받침 없음
    assert scorer.with_subject("일정") == "일정이"
    assert scorer.with_subject("CS101") == "CS101가"        # 한글이 아니면 가
