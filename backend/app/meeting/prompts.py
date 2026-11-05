"""라운드 하나를 말로 옮기는 프롬프트.

**모델은 판단을 하지 않는다.** 어느 후보를 제안할지, 누가 수락하고 누가
거절할지는 이미 점수가 정했다(scorer.py). 여기서는 그 결과를 사람 말로
바꾸기만 한다. 모델에게 판단을 맡기면 같은 데이터로 다른 시간이 나와서
리허설과 본 시연이 어긋난다.

한 라운드를 한 번에 요청한다. 발언마다 부르면 조율 한 번에 15~30번이
되어 한도와 시간을 다 쓴다.

**토큰을 아끼게 짧게 쓴다.** 무료 한도로 시연과 리허설을 다 돌려야 한다.
처음 판본은 라운드당 1760 토큰(입력 1312 + 출력 448)을 썼다. 줄인 방법:

- 상태 JSON을 indent 없이 보낸다. 들여쓰기 공백이 그대로 토큰이다
- 키를 짧게(`이름`→`n`). 값은 한국어 그대로 둔다 — 뜻이 없어지면 말이 나빠진다
- 규칙을 산문에서 한 줄짜리로. 모델은 번호 목록을 산문만큼 잘 따른다
- 발언을 한 문장으로 묶는다. 출력 토큰이 절반이 된다
- 출력 JSON을 한 줄로 받는다

**기능 규칙은 하나도 빼지 않았다** — 판정 유지, 숫자 금지, 근거 살리기,
1라운드만 어필, 2라운드부터 무엇을 바꿨는지, 모두가 responses에 한 번.
짧게 만든 것은 말투 안내뿐이다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

_WEEKDAYS = "월화수목금토일"


def when(start_at, end_at) -> str:
    """11월 9일(월) 15:00–17:00"""
    return (
        f"{start_at.month}월 {start_at.day}일({_WEEKDAYS[start_at.weekday()]}) "
        f"{start_at:%H:%M}–{end_at:%H:%M}"
    )


def yield_step(total: int) -> str:
    """누적 양보는 숫자로 내보내지 않는다(명세 권장 규칙 3). 단계로만 말한다."""
    if total <= 0:
        return "아직 없음"
    if total <= 2:
        return "조금 맞춰 줌"
    return "많이 맞춰 줌"


@dataclass(frozen=True)
class Speaker:
    """한 사람이 이 후보에 대해 어떤 상태인가. 전부 계산된 값이다."""

    user_id: int
    name: str
    score: int  # 1~5
    available: bool
    reason: str  # "알바와 겹칩니다" 같은, 이미 한국어인 근거
    accepts: bool  # 점수가 정한 결과. 모델이 뒤집으면 안 된다
    yield_step: str  # "아직 없음" / "조금 맞춰 줌" / "많이 맞춰 줌"
    yield_rank: int  # 누적 양보 원래 숫자. 누구를 꺾을지 정할 때만 쓴다


def round_prompt(
    *,
    topic: str,
    slot: str,
    round_no: int,
    speakers: list[Speaker],
    last_round_rejections: list[str],
    appeals: dict[str, str],
) -> str:
    """판단 에이전트 1개 + 팀원 n개를 한 번에 받는 프롬프트."""
    상황 = {
        "주제": topic,
        "제안시간": slot,
        "라운드": round_no,
        "원한시간": appeals,
        "지난거절": last_round_rejections,
        "사람": [
            {
                "id": s.user_id,
                "n": s.name,
                "판정": "수락" if s.accepts else "거절",
                "근거": s.reason,
                "불편": s.score,
                "누적양보": s.yield_step,
                **({"못옴": True} if not s.available else {}),
            }
            for s in speakers
        ],
    }
    # indent 없이, 공백 없이. 들여쓰기와 ", "의 공백이 그대로 토큰이다.
    자료 = json.dumps(상황, ensure_ascii=False, separators=(",", ":"))

    # 1라운드에만 어필이 있다. 2라운드부터는 판단이 먼저 무엇을 바꿨는지
    # 말하므로 appeals가 빈 배열이어야 한다.
    어필규칙 = (
        '"appeals"에 사람마다 하나. "원한시간"의 자기 시간을 말한다.'
        if round_no == 1
        else '"appeals"는 빈 배열. "judge"가 "지난거절"을 받아 무엇을 바꿨는지'
        " 먼저 말하고, 거절하는 사람은 다음에 원하는 시간도 한 문장에 적는다."
    )

    return f"""대학 팀플 일정 조율 화면에 나갈 대화를 쓴다. 상황:
{자료}

규칙:
- "판정"대로 쓴다. 다시 판단하지 않는다.
- "불편" 숫자를 문장에 넣지 않는다. 참고용이다.
- "근거"가 그 사람이 그렇게 말하는 이유다. 살려 쓴다.
- 존댓말, 1인칭, 한 사람당 한 문장. "judge"는 한두 문장.
- "judge"는 왜 이 시간인지 말한다. "누적양보"가 많이 맞춰 줌인 사람을 먼저 챙겼다고 말해도 된다.
- "못옴"이 참인 사람은 그 시간에 올 수 없다.
- "responses"에 "사람" 전원이 한 번씩 들어간다.
- {어필규칙}

공백 없는 JSON 한 줄만 출력한다. 코드 블록 금지.
{{"appeals":[{{"user_id":1,"text":"..."}}],"judge":"...","responses":[{{"user_id":1,"text":"..."}}]}}"""
