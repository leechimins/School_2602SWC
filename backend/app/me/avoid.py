"""온보딩 질문 4 한 줄에서 문장과 구간을 함께 뽑는다.

사람은 한 줄만 적고 모델은 한 번만 일한다. 그 한 번이 두 가지를 낸다:

    "금요일 저녁은 알바 끝나고 바로라 피하고 싶어요"
        ↓
    polished  "금요일 저녁은 개인 일정이 있어 어렵습니다"   → 발언에 쓴다
    weekdays  [4]  start 1080  end 1320                   → 점수에 쓴다(불편 +2)

**구조를 못 뽑는 경우가 흔하다.** "너무 이른 시간은 싫어요"처럼 요일이 없거나
범위가 모호한 말이다. 그때 억지로 숫자를 만들면 엉뚱한 시간이 거절된다.
그래서 못 뽑으면 문장만 돌려주고 점수는 안 건드린다 — 발언에는 쓰이니 값이
없는 건 아니다.

**사적인 사유는 여기서 뭉갠다.** 자유 입력이라 "집에 아픈 사람이 있어서"가
들어올 수 있고, 다듬지 않으면 그게 조율 발언으로 팀 전체에 나간다. 프롬프트가
그걸 "개인 일정"으로 바꾸게 한다. 프롬프팅은 대체로 막고 보장은 아니라서,
다듬은 문장을 사람이 보고 고칠 수 있게 PATCH /me/preferences가 열려 있다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.shared import llm

# 요일 이름은 프롬프트에만 있다. 0 = 월요일(파이썬 weekday와 같다).
_PROMPT = """다음은 대학생이 "피하고 싶은 시간"에 적은 한 줄이다.

"{raw}"

두 가지를 만든다.
1. sentence: 팀원에게 보일 한 문장. 존댓말. 건강·가족·금전처럼 사적인 사유는
   "개인 일정"으로 바꾼다. 무슨 일인지 팀에 알릴 이유가 없다.
2. 요일과 시각. **확실할 때만** 숫자를 낸다. 애매하면 null.
   weekdays: 0=월 … 6=일. "평일"은 [0,1,2,3,4].
   start/end: 자정부터 분. 저녁 6시 = 1080. start < end.
   "저녁"은 1080~1320, "오전"은 540~720, "아침"은 360~540, "밤"은 1260~1440.

공백 없는 JSON 한 줄만. 코드 블록 금지.
{{"sentence":"...","weekdays":[4],"start":1080,"end":1320}}"""


@dataclass(frozen=True)
class Avoid:
    """다듬은 문장과, 뽑혔다면 구간. 구간은 셋이 함께 있거나 함께 없다."""

    polished: str
    weekdays: list[int] | None = None
    start_min: int | None = None
    end_min: int | None = None


def interpret(raw: str | None) -> Avoid | None:
    """한 줄을 해석한다. 빈 줄이거나 모델이 실패하면 None.

    None이면 부르는 쪽은 avoid_polished와 구간을 전부 비운다. 원문을 복사해
    넣지 않는다 — 다듬지 않은 말이 그대로 팀에 나가는 게 이 함수가 막으려는
    바로 그 일이다.
    """
    text = (raw or "").strip()
    if not text:
        return None

    answer = llm.complete_json(_PROMPT.format(raw=text), max_tokens=200)
    if not answer:
        return None

    sentence = str(answer.get("sentence") or "").strip()
    if not sentence:
        return None

    days, start, end = _range(answer)
    return Avoid(polished=sentence[:200], weekdays=days, start_min=start, end_min=end)


def _range(answer: dict) -> tuple[list[int] | None, int | None, int | None]:
    """구간 셋을 검사한다. 하나라도 이상하면 셋 다 버린다.

    반쯤 맞는 구간이 가장 나쁘다 — 요일만 맞고 시각이 틀리면 하루가 통째로
    벌점을 받는다. 셋이 다 맞을 때만 점수에 들어간다.
    """
    raw_days = answer.get("weekdays")
    if not isinstance(raw_days, list) or not raw_days:
        return None, None, None
    days = []
    for d in raw_days:
        if not isinstance(d, int) or isinstance(d, bool) or not 0 <= d <= 6:
            return None, None, None
        if d not in days:
            days.append(d)

    start, end = answer.get("start"), answer.get("end")
    for v in (start, end):
        if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 1440:
            return None, None, None
    assert isinstance(start, int) and isinstance(end, int)
    if start >= end:
        return None, None, None

    return sorted(days), start, end
