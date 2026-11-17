"""수락·거절 때 남긴 한 줄로 내 선호를 고친다. 에이전트가 나를 배우는 길.

    "오전엔 수업 끝나자마자라 힘들어요" (목 10:00 회의를 거절하며)
        ↓ 모델이 해석 — 무엇을 바꿀지 하나만 고른다
    avoid  목 540~720  "다음부터 목요일 오전은 피할게요"
        ↓ 규칙으로 검사하고 반영
    preference 갱신 + preference_change 한 행(전·후 값)

**판단은 규칙이 한다.** 모델은 말을 구조로 바꾸기만 한다. 고칠 수 있는 칸은
셋(피하는 시간 · 좋은 시간대 · 대면/비대면)이고 값은 avoid.py와 같은 검사를
지난 것만 들어간다. 애매하면 아무것도 안 바꾼다.

**말없이 바꾸지 않는다.** 바꾸면 반드시 행을 남기고 응답에 실어 보낸다.
화면은 "다음부터 … · 되돌리기"를 보여 준다. 되돌리기는 before를 다시 쓴다.

**지금 조율에는 안 들어간다.** 다시 조율은 저장된 점수를 그대로 쓴다
(rerun.py). 바뀐 선호는 다음 조율부터 점수에 들어간다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException, status
from sqlmodel import Session, col, select

from app.me import avoid
from app.me.models import Preference
from app.meeting.models import PreferenceChange
from app.shared import llm
from app.shared.base import KST, real_now
from app.shared.enums import Daypart, Mode

_WEEKDAYS = "월화수목금토일"

_PROMPT = """대학생이 팀 회의 시간 제안에 {answer}하며 남긴 한 줄이다.
제안된 회의: {weekday}요일 {hh:02d}:{mm:02d} 시작.
한 줄: "{text}"

이 사람의 다음 회의 선호를 **하나만** 고친다. 확실하지 않으면 field는 null.
- "avoid": 피하고 싶은 요일·시각. weekdays 0=월…6=일, start/end는 자정부터 분(start<end).
  "오전" 540~720, "점심" 720~840, "오후" 840~1080, "저녁" 1080~1320, "아침" 360~540.
  요일을 말하지 않았으면 제안된 회의의 요일을 쓴다.
  sentence: 팀원에게 보일 한 문장(존댓말). 건강·가족·금전 같은 사적 사유는 "개인 일정"으로.
- "dayparts": 좋은 시간대 목록. morning(6~9시) forenoon(9~12) lunch(12~14) afternoon(14~18) evening(18~21) night(21~24).
- "mode_pref": offline(대면) · online(비대면) · any.
시간과 상관없는 말("수고했어요", "자료 제가 준비할게요")이면 field는 null.

summary: 에이전트가 본인에게 하는 한 줄. "다음부터 목요일 오전은 피할게요"처럼.

공백 없는 JSON 한 줄만. 코드 블록 금지.
{{"field":"avoid","weekdays":[3],"start":540,"end":720,"sentence":"...","dayparts":null,"mode_pref":null,"summary":"..."}}"""


@dataclass(frozen=True)
class Learned:
    """고칠 칸 하나와 새 값. avoid면 (요일, 시작, 끝, 문장), 아니면 열 값 그대로."""

    field: str
    value: object
    summary: str


FIELDS = ("avoid", "dayparts", "mode_pref")


def interpret(text: str | None, meeting_start: datetime, accepted: bool) -> Learned | None:
    """한 줄을 해석한다. 빈 줄·모델 실패·애매함·검사 탈락이면 None."""
    text = (text or "").strip()
    if not text:
        return None
    local = meeting_start.astimezone(KST)
    answer = llm.complete_json(
        _PROMPT.format(
            answer="수락" if accepted else "거절",
            weekday=_WEEKDAYS[local.weekday()],
            hh=local.hour,
            mm=local.minute,
            text=text,
        ),
        max_tokens=300,
    )
    if not answer:
        return None
    summary = str(answer.get("summary") or "").strip()[:200]
    field = answer.get("field")
    if not summary or field not in FIELDS:
        return None

    if field == "avoid":
        days, start, end = avoid._range(answer)
        sentence = str(answer.get("sentence") or "").strip()[:100]
        # 구간이 반쯤 맞으면 엉뚱한 시간이 벌점을 받는다. 셋 다 맞아야 들어간다.
        if days is None or not sentence:
            return None
        return Learned("avoid", (days, start, end, sentence), summary)
    if field == "dayparts":
        raw = answer.get("dayparts")
        if not isinstance(raw, list) or not raw or not all(p in Daypart._value2member_map_ for p in raw):
            return None
        order = list(Daypart)
        return Learned("dayparts", sorted({Daypart(p) for p in raw}, key=order.index), summary)
    if answer.get("mode_pref") not in Mode._value2member_map_:
        return None
    return Learned("mode_pref", Mode(answer["mode_pref"]), summary)


def _snapshot(pref: Preference, field: str) -> str | None:
    """before·after에 적는 값. 열이 200자라 칸마다 사람이 읽는 값 하나만 적는다.

    피하는 시간은 원문(avoid_raw)만 적는다. 되돌릴 때 원문을 다시 해석해 문장과
    구간을 만든다 — 내 조건 화면에서 원문을 고칠 때(PATCH)와 같은 길이다.
    """
    if field == "avoid":
        return pref.avoid_raw
    if field == "dayparts":
        return ",".join(pref.dayparts) if pref.dayparts else None
    return pref.mode_pref


def _apply_avoid(pref: Preference, days: list[int], start: int, end: int, sentence: str) -> bool:
    """피하는 시간을 넣는다. 원래 있던 조건을 지우지 않는다.

    칸이 구간 하나뿐이다. 비어 있으면 넣고, 같은 시각대면 요일만 더한다
    (금 저녁 + 목 저녁). 다른 시각대가 이미 있으면 바꾸지 않는다 — 알바처럼
    사람이 직접 적은 조건을 피드백 한 줄이 덮으면 안 된다.
    """
    has_range = pref.avoid_weekdays and pref.avoid_start_min is not None
    if not has_range:
        pref.avoid_raw = pref.avoid_polished = sentence
        pref.avoid_weekdays, pref.avoid_start_min, pref.avoid_end_min = days, start, end
        return True
    if (pref.avoid_start_min, pref.avoid_end_min) != (start, end):
        return False
    merged = sorted(set(pref.avoid_weekdays or []) | set(days))
    if merged == sorted(pref.avoid_weekdays or []):
        return False
    pref.avoid_weekdays = merged
    pref.avoid_raw = f"{pref.avoid_raw or ''} / {sentence}".strip(" /")[:200]
    pref.avoid_polished = f"{pref.avoid_polished or ''} / {sentence}".strip(" /")[:200]
    return True


def learn(
    db: Session, user_id: int, meeting_id: int, text: str | None, meeting_start: datetime, accepted: bool
) -> PreferenceChange | None:
    """해석해서 바뀌는 게 있으면 반영하고 기록을 남긴다. 아무것도 안 바뀌면 None."""
    learned = interpret(text, meeting_start, accepted)
    if learned is None:
        return None
    pref = db.exec(select(Preference).where(Preference.user_id == user_id)).first()
    if pref is None:
        pref = Preference(user_id=user_id)
    before = _snapshot(pref, learned.field)
    if learned.field == "avoid":
        days, start, end, sentence = learned.value  # type: ignore[misc]
        if not _apply_avoid(pref, days, start, end, sentence):
            return None
    else:
        setattr(pref, learned.field, learned.value)
    after = _snapshot(pref, learned.field)
    if before == after:
        return None
    pref.updated_at = real_now()
    change = PreferenceChange(
        user_id=user_id,
        meeting_id=meeting_id,
        source_text=(text or "").strip()[:200],
        field=learned.field,
        before=before,
        after=after,
        summary=learned.summary,
    )
    db.add(pref)
    db.add(change)
    db.commit()
    db.refresh(change)
    return change


def recent(db: Session, user_id: int, limit: int = 10) -> list[PreferenceChange]:
    return list(
        db.exec(
            select(PreferenceChange)
            .where(PreferenceChange.user_id == user_id)
            .order_by(col(PreferenceChange.created_at).desc(), col(PreferenceChange.id).desc())
            .limit(limit)
        ).all()
    )


def undo(db: Session, user_id: int, change_id: int) -> PreferenceChange:
    """before를 다시 쓴다. 그 뒤에 같은 칸이 또 바뀌었으면 409 — 나중 변경을 덮지 않는다."""
    change = db.get(PreferenceChange, change_id)
    if change is None or change.user_id != user_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "없는 변경입니다."},
        )
    if change.reverted:
        return change
    pref = db.exec(select(Preference).where(Preference.user_id == user_id)).first()
    if pref is None or _snapshot(pref, change.field) != change.after:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "CHANGED_SINCE", "message": "그 뒤에 다시 바뀌어서 되돌릴 수 없어요."},
        )
    if change.field == "avoid":
        result = avoid.interpret(change.before)
        # 원문은 있는데 해석을 못 하면 되돌리지 않는다. 그대로 두면 사람이 적은
        # 구간(알바 등)이 같이 지워진다.
        if change.before and result is None:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "AI_UNAVAILABLE", "message": "잠시 뒤 다시 되돌려 주세요."},
            )
        pref.avoid_raw = change.before
        pref.avoid_polished = result.polished if result else None
        pref.avoid_weekdays = result.weekdays if result else None
        pref.avoid_start_min = result.start_min if result else None
        pref.avoid_end_min = result.end_min if result else None
    elif change.field == "dayparts":
        pref.dayparts = [Daypart(p) for p in change.before.split(",")] if change.before else None
    else:
        pref.mode_pref = Mode(change.before) if change.before else None
    pref.updated_at = real_now()
    change.reverted = True
    db.add(pref)
    db.add(change)
    db.commit()
    db.refresh(change)
    return change
