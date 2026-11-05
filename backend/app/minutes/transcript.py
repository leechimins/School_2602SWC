"""원문 다루기 — 직접 쓴 글을 줄로 나누고 말한 사람을 가린다.

AI를 쓰지 않는다. 받아적기(STT)가 안 될 때 끝까지 가는 길이라
여기서 모델을 부르면 안 된다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import delete
from sqlmodel import Session

from app.minutes.models import TranscriptSegment

# "지수: 내용" / "지수 : 내용" / 전각 콜론. 이름은 user.name 길이(20)까지.
_SPEAKER = re.compile(r"^\s*([^:：]{1,20}?)\s*[:：]\s*(.*)$")


@dataclass(frozen=True)
class Line:
    speaker_user_id: int | None
    text: str


def parse(text: str, members: dict[str, int]) -> list[Line]:
    """원문을 줄로 나눈다. 빈 줄은 버린다.

    `이름:` 앞부분이 이 방 팀원 이름일 때만 화자로 본다. 아니면 줄 전체를
    화자 없이 둔다 — "참고: 다음 주 휴강"처럼 콜론이 들어간 보통 문장을
    사람으로 잘못 읽지 않으려는 것이다.
    """
    lines: list[Line] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        match = _SPEAKER.match(stripped)
        if match and match.group(1) in members:
            body = match.group(2).strip()
            if body:
                lines.append(Line(members[match.group(1)], body))
            continue
        lines.append(Line(None, stripped))
    return lines


def replace(db: Session, meeting_id: int, lines: list[Line]) -> None:
    """원문을 통째로 바꾼다. 줄 번호는 0부터 다시 매긴다.

    지우고 다시 넣는다. 직접 쓰기는 글 전체를 보내는 방식이라 어느 줄이
    바뀌었는지 맞춰 볼 필요가 없다.
    """
    db.exec(delete(TranscriptSegment).where(TranscriptSegment.meeting_id == meeting_id))
    db.add_all(
        TranscriptSegment(
            meeting_id=meeting_id,
            seq=seq,
            speaker_user_id=line.speaker_user_id,
            text=line.text,
        )
        for seq, line in enumerate(lines)
    )
