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

from typing import Literal

from fastapi import HTTPException, status

from app.meeting.models import Meeting
from app.shared.enums import TranscriptMode

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
