"""받아적기(STT) — 시작·조각 쌓기·멈추기·말한 사람 정하기. 레인 B.

**엔진을 모른다.** 서버는 "번호 + 화자 라벨 + 글자" 줄만 받는다. 브라우저가
엔진에서 받은 글자를 보내든, 서버가 엔진을 불러 글자로 바꾼 뒤 이 함수로
넣든 같다. 엔진을 바꿔도 이 파일은 안 고친다. 음성은 저장하지 않는다.

상태는 meeting의 칸 셋으로만 본다(B가 채우는 칸이다).

- 시작 전: transcript_mode가 stt가 아니거나 recording_started_at이 비어 있음
- 받아적는 중: 시작 시각만 있음
- 멈춤: 멈춘 시각까지 있음. 다시 시작할 수 없다 — 번호와 원문이 섞인다
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import Session, select

from app.meeting.models import Meeting
from app.minutes.models import TranscriptSegment
from app.shared.base import real_now
from app.shared.enums import TranscriptMode

# 빠진 번호를 알려 줄 때 앞에서부터 이만큼만. 프론트는 이것부터 다시 보낸다.
MAX_MISSING = 100

RecordingState = Literal["none", "recording", "stopped"]


def state(meeting: Meeting) -> RecordingState:
    if meeting.transcript_mode != TranscriptMode.STT or meeting.recording_started_at is None:
        return "none"
    if meeting.recording_stopped_at is None:
        return "recording"
    return "stopped"


def conflict(code: str, message: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail={"code": code, "message": message})


def stopped_error() -> HTTPException:
    return conflict("RECORDING_STOPPED", "이미 받아적기를 마쳤어요.")


def not_recording_error() -> HTTPException:
    return conflict("NOT_RECORDING", "받아적기를 먼저 시작해 주세요.")


@dataclass(frozen=True)
class Piece:
    seq: int
    speaker_label: str | None
    text: str


@dataclass(frozen=True)
class Stacked:
    added: int
    skipped: int
    last_seq: int
    missing: list[int]


def stack(db: Session, meeting_id: int, pieces: list[Piece]) -> Stacked:
    """조각을 쌓는다. 같은 번호는 처음 온 것만 남기고 건너뛴다. 커밋은 부르는 쪽.

    (meeting_id, seq) 유일 제약에 기대 ON CONFLICT DO NOTHING으로 넣는다 —
    같은 조각이 두 요청으로 동시에 와도 한 줄만 남는다. 원문은 언제나 번호 순으로
    읽으므로(회의록 보기·요약) 순서가 섞여 와도 상관없다.
    """
    rows: dict[int, Piece] = {}
    for piece in pieces:
        text = piece.text.strip()
        if text and piece.seq not in rows:
            rows[piece.seq] = Piece(piece.seq, piece.speaker_label or None, text)

    added = 0
    if rows:
        # 기록용 시각이라 시연 시계가 아니라 실제 시각이다(created_at 기본값과 같다).
        # 한 문장 insert라 모델의 기본값이 안 붙어서 직접 넣는다.
        now = real_now()
        inserted = db.execute(
            pg_insert(TranscriptSegment)
            .values(
                [
                    {
                        "meeting_id": meeting_id,
                        "seq": p.seq,
                        "speaker_label": p.speaker_label,
                        "text": p.text,
                        "created_at": now,
                    }
                    for p in rows.values()
                ]
            )
            .on_conflict_do_nothing(index_elements=["meeting_id", "seq"])
            # 여러 행을 넣으면 rowcount가 -1일 수 있어 실제로 들어간 행을 받는다(notify.py와 같다)
            .returning(TranscriptSegment.seq)  # type: ignore[arg-type]
        ).all()
        added = len(inserted)

    seqs = set(
        db.exec(
            select(TranscriptSegment.seq).where(TranscriptSegment.meeting_id == meeting_id)
        ).all()
    )
    last = max(seqs) if seqs else -1
    missing = [n for n in range(last + 1) if n not in seqs][:MAX_MISSING]
    return Stacked(added=added, skipped=len(pieces) - added, last_seq=last, missing=missing)
