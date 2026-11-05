"""회의록 요약 · 할 일 뽑기 — AI 쪽.

모델은 한 번만 부른다. 주제 한 줄 + 결정/논의/보류 + 할 일 제안을 한
JSON으로 받는다. 모델이 준 것을 그대로 믿지 않고 여기서 검증한다.

- 모든 항목은 근거 줄 번호(`lines`)를 단다. 원문에 있는 줄을 하나도 못
  가리키면 버린다. 줄 번호는 검증에만 쓰고 저장하지 않는다(원문 점프 없음).
- 담당자는 이 방 팀원 이름이고, 근거 줄에 그 이름이 나오거나 그 사람이
  말한 줄일 때만 채운다. 아니면 담당자 없음 — 정상 시작 상태다.
- 기한은 `YYYY-MM-DD`만 받는다. "다음 주 목요일"은 프롬프트에 준 회의
  날짜를 기준으로 모델이 계산한다.

호출(`llm.complete_json`)과 검증·저장을 함수로 나눠서, 테스트는 모델
응답만 바꿔 끼운다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlmodel import Session, col, select

from app.meeting.models import Meeting
from app.minutes.models import Minutes, MinutesItem, Task, TranscriptSegment
from app.shared import llm
from app.shared.base import KST
from app.shared.enums import MinutesItemKind, MinutesStatus, TaskOrigin, TaskState

# 모델에 넘기는 원문 상한. 1시간 회의 받아적기가 대략 1만 자다.
MAX_TRANSCRIPT_CHARS = 20_000
MAX_ITEMS_PER_KIND = 6
MAX_SUGGESTIONS = 8
MAX_ITEM_CHARS = 200
MAX_TITLE_CHARS = 200
MAX_HEADLINE_CHARS = 100
# 요약 넷 + 제안 여덟에 근거 줄 번호까지. 실제 출력은 이보다 한참 짧다.
MAX_TOKENS = 2000

WEEKDAYS = "월화수목금토일"
KINDS = {
    "decisions": MinutesItemKind.DECISION,
    "discussions": MinutesItemKind.DISCUSSION,
    "pendings": MinutesItemKind.PENDING,
}


@dataclass
class SuggestionDraft:
    title: str
    assignee_user_id: int | None
    due_date: date | None


@dataclass
class Draft:
    """검증을 통과한 결과. 저장 직전 모양."""

    headline: str
    items: dict[MinutesItemKind, list[str]] = field(default_factory=dict)
    suggestions: list[SuggestionDraft] = field(default_factory=list)


@dataclass
class Line:
    seq: int
    speaker_user_id: int | None
    speaker_name: str | None
    text: str


# ── 프롬프트 ────────────────────────────────────────────────────────


def build_prompt(
    *,
    topic: str,
    held_on: date,
    lines: list[Line],
    member_names: list[str],
    confirmed_titles: list[str],
) -> str:
    transcript = "\n".join(
        f"[{line.seq}] {line.speaker_name or '(모름)'}: {line.text}" for line in lines
    )[:MAX_TRANSCRIPT_CHARS]
    confirmed = "\n".join(f"- {t}" for t in confirmed_titles) or "(없음)"
    return f"""너는 대학생 팀 프로젝트의 회의록을 정리한다. 아래 원문만 근거로 쓴다.

회의 주제: {topic}
회의 날짜: {held_on.isoformat()} ({WEEKDAYS[held_on.weekday()]}요일)
팀원: {", ".join(member_names)}

원문 (줄마다 [줄 번호] 말한 사람: 발언):
{transcript}

이미 확정된 할 일 (다시 제안하지 않는다):
{confirmed}

다음 JSON 객체 하나만 출력한다. 설명이나 코드 울타리를 붙이지 않는다.
{{
  "headline": "회의에서 한 일을 한 줄로 (40자 이내)",
  "decisions": [{{"text": "정해진 것", "lines": [줄 번호]}}],
  "discussions": [{{"text": "이야기했지만 정하지 않은 것", "lines": [줄 번호]}}],
  "pendings": [{{"text": "다음으로 미룬 것", "lines": [줄 번호]}}],
  "tasks": [{{"title": "할 일 (동사로 끝나는 짧은 구)", "assignee": "팀원 이름 또는 null", "due_date": "YYYY-MM-DD 또는 null", "lines": [줄 번호]}}]
}}

규칙:
- 원문은 대화일 수도 있고, 한 사람이 급히 적은 메모(말한 사람 모름, 줄임말, 기호)일 수도 있다. 메모에서 일 옆에 적힌 팀원 이름은 그 일을 맡은 사람이다.
- 다음 회의로 미루거나 아직 정하지 않은 것은 decisions가 아니라 pendings에 넣는다.
- 담당자가 정해지지 않았어도 누군가 해야 하는 일이면 tasks에 넣는다(assignee는 null). 담당자를 아직 못 정한 일을 pendings에만 두고 tasks에서 빼지 않는다.
- 모든 항목의 lines에는 그 항목의 근거가 되는 원문 줄 번호를 적는다. 근거가 없으면 항목을 만들지 않는다.
- 묶음마다 항목은 {MAX_ITEMS_PER_KIND}개 이하, tasks는 {MAX_SUGGESTIONS}개 이하. 없으면 빈 배열.
- assignee는 원문에서 그 사람이 맡겠다고 했거나 맡기로 분명히 정해진 경우에만 팀원 이름을 그대로 쓴다. 애매하면 null.
- due_date는 원문에 기한이 나온 경우에만 쓴다. "다음 주 목요일", "이번 주말" 같은 말은 회의 날짜를 기준으로 날짜를 계산한다. 없으면 null.
- 요약 항목은 누가 무엇을 하는지 드러나게 쓴다. 예: "발표는 민지가 맡음", "발표 대본 담당은 아직 없음".
- 이미 확정된 할 일과 같은 일이면 표현이 달라도 tasks에 넣지 않는다.
- 문장은 한국어로, 짧게 쓴다.
"""


def request(prompt: str) -> dict | None:
    """모델 호출. 실패하면 None (llm.complete_json은 예외를 올리지 않는다)."""
    return llm.complete_json(prompt, max_tokens=MAX_TOKENS)


# ── 검증 ────────────────────────────────────────────────────────────


def _clean(value: object, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text[:limit] if text else None


def _evidence(value: object, by_seq: dict[int, Line]) -> list[Line]:
    """근거 줄 번호 중 원문에 실제로 있는 줄만."""
    if not isinstance(value, list):
        return []
    found = []
    for seq in value:
        # bool은 int의 하위형이라 따로 막는다
        if isinstance(seq, int) and not isinstance(seq, bool) and seq in by_seq:
            found.append(by_seq[seq])
    return found


def _assignee(value: object, evidence: list[Line], names: dict[str, int]) -> int | None:
    name = _clean(value, 50)
    if name is None or name not in names:
        return None
    user_id = names[name]
    if any(line.speaker_user_id == user_id or name in line.text for line in evidence):
        return user_id
    return None


# 이 글자 수보다 짧은 제목은 포함 관계로 겹침을 보지 않는다 ("조사"가 다 걸림)
MIN_OVERLAP_CHARS = 4


def _same_task(a: str, b: str) -> bool:
    """이미 있는 할 일과 같은 일인지. 모델이 "발표 슬라이드 초안"을
    "발표 슬라이드 초안 작성"으로 바꿔 다시 내는 일이 실제로 있었다.
    공백을 빼고 한쪽이 다른 쪽을 통째로 담으면 같은 일로 본다."""
    x, y = "".join(a.split()), "".join(b.split())
    if x == y:
        return True
    short, long = sorted((x, y), key=len)
    return len(short) >= MIN_OVERLAP_CHARS and short in long


def _due(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def parse(
    raw: dict | None,
    *,
    lines: list[Line],
    names: dict[str, int],
    confirmed_titles: list[str],
) -> Draft | None:
    """모델 응답을 검증한다. 뼈대가 깨졌으면 None — 부르는 쪽이 실패로 처리한다.

    뼈대(headline 문자열, 네 묶음이 배열)만 맞으면 항목 하나하나가 깨진
    것은 그 항목만 버린다.
    """
    if not isinstance(raw, dict):
        return None
    headline = _clean(raw.get("headline"), MAX_HEADLINE_CHARS)
    if headline is None:
        return None
    if not all(isinstance(raw.get(key), list) for key in (*KINDS, "tasks")):
        return None

    by_seq = {line.seq: line for line in lines}
    draft = Draft(headline=headline)

    for key, kind in KINDS.items():
        texts: list[str] = []
        for entry in raw[key]:
            if not isinstance(entry, dict):
                continue
            text = _clean(entry.get("text"), MAX_ITEM_CHARS)
            if text and _evidence(entry.get("lines"), by_seq) and text not in texts:
                texts.append(text)
        draft.items[kind] = texts[:MAX_ITEMS_PER_KIND]

    seen = list(confirmed_titles)
    for entry in raw["tasks"]:
        if not isinstance(entry, dict):
            continue
        title = _clean(entry.get("title"), MAX_TITLE_CHARS)
        evidence = _evidence(entry.get("lines"), by_seq)
        if not title or not evidence or any(_same_task(title, t) for t in seen):
            continue
        seen.append(title)
        draft.suggestions.append(
            SuggestionDraft(
                title=title,
                assignee_user_id=_assignee(entry.get("assignee"), evidence, names),
                due_date=_due(entry.get("due_date")),
            )
        )
    draft.suggestions = draft.suggestions[:MAX_SUGGESTIONS]
    return draft


# ── 저장 ────────────────────────────────────────────────────────────


def load_lines(db: Session, meeting_id: int, names_by_id: dict[int, str]) -> list[Line]:
    segments = db.exec(
        select(TranscriptSegment)
        .where(TranscriptSegment.meeting_id == meeting_id)
        .order_by(TranscriptSegment.seq)
    ).all()
    return [
        Line(
            seq=s.seq,
            speaker_user_id=s.speaker_user_id,
            speaker_name=names_by_id.get(s.speaker_user_id) if s.speaker_user_id else None,
            text=s.text,
        )
        for s in segments
    ]


def confirmed_titles(db: Session, meeting_id: int) -> list[str]:
    return list(
        db.exec(
            select(Task.title).where(
                Task.meeting_id == meeting_id,
                col(Task.confirmed).is_(True),
                col(Task.dropped).is_(False),
            )
        ).all()
    )


def held_on(meeting: Meeting) -> date:
    return meeting.start_at.astimezone(KST).date()


def save(db: Session, meeting: Meeting, draft: Draft) -> None:
    """요약을 통째로 바꾸고, 확정 전 AI 제안을 새 제안으로 바꾼다.

    이미 확정된 할 일과 직접 추가한 할 일은 건드리지 않는다. 지난 제안은
    지우지 않고 "필요 없음"으로 둔다. 커밋하지 않는다.

    회의록 행을 잠근다. 두 폰에서 동시에 다시 하기를 누르면 뒤에 온 쪽이
    앞쪽 저장을 본 뒤 그 제안을 버리고 자기 것을 넣는다 — 제안이 두 벌
    쌓이지 않는다.
    """
    assert meeting.id is not None
    minutes = db.exec(
        select(Minutes).where(Minutes.meeting_id == meeting.id).with_for_update()
    ).one()
    minutes.headline = draft.headline
    minutes.status = MinutesStatus.DONE
    db.add(minutes)

    for old in db.exec(select(MinutesItem).where(MinutesItem.minutes_id == minutes.id)).all():
        db.delete(old)
    db.flush()
    seq = 0
    for kind, texts in draft.items.items():
        for text in texts:
            db.add(MinutesItem(minutes_id=minutes.id, kind=kind, seq=seq, text=text))
            seq += 1

    stale = db.exec(
        select(Task).where(
            Task.meeting_id == meeting.id,
            Task.origin == TaskOrigin.AI,
            col(Task.confirmed).is_(False),
            col(Task.dropped).is_(False),
        )
    ).all()
    for task in stale:
        task.dropped = True
        db.add(task)

    for suggestion in draft.suggestions:
        db.add(
            Task(
                room_id=meeting.room_id,
                meeting_id=meeting.id,
                title=suggestion.title,
                due_date=suggestion.due_date,
                assignee_user_id=suggestion.assignee_user_id,
                state=TaskState.TODO,
                origin=TaskOrigin.AI,
                confirmed=False,
            )
        )
