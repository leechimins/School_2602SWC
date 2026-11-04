"""회의록 · 할 일 제안 · 할 일. 레인 B.

한 방 안의 일이라 prefix가 `/rooms/{room_id}`다.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.meeting.models import Meeting
from app.minutes import transcript
from app.minutes.record import RECORDABLE, meeting_detail, meeting_list, member_names
from app.minutes.schemas import MeetingDetailOut, MeetingListOut, RecordStartIn, TranscriptIn
from app.shared import demo_clock
from app.shared.auth import current_user_id, require_member
from app.shared.db import session_dep
from app.shared.enums import MeetingStatus, TranscriptMode

router = APIRouter(prefix="/rooms/{room_id}", tags=["minutes"])

# 잡힌 회의 없이 바로 기록을 시작할 때 회의 길이. 끝 시각 칸이 NOT NULL이고
# start_at < end_at 제약이 있어서 자리만 채운다. 화면은 이 값을 쓰지 않는다.
ADHOC_MEETING_LENGTH = timedelta(hours=1)


def _meeting(db: Session, room_id: int, meeting_id: int) -> Meeting:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None or meeting.room_id != room_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "그 회의가 없습니다."},
        )
    return meeting


@router.get("/meetings", response_model=MeetingListOut, summary="회의록 목록 보기")
def list_meetings(
    room_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> MeetingListOut:
    """확정된 회의와 지난 회의. 최근 회의가 먼저입니다.

    - 회의안(조율 중)과 취소된 회의는 나오지 않습니다.
    - 주제 한 줄(`headline`)은 요약 뒤에 생깁니다. 그 전에는 `topic`을 보여 주세요.
    """
    require_member(db, room_id, user_id)
    return MeetingListOut(meetings=meeting_list(db, room_id))


@router.post(
    "/meetings",
    response_model=MeetingDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="회의 기록 시작하기",
)
def start_record(
    room_id: int,
    body: RecordStartIn,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> MeetingDetailOut:
    """잡힌 회의에 기록을 붙이거나, 잡힌 회의 없이 회의를 새로 만듭니다.

    - `meeting_id`가 있으면 그 회의를 돌려줍니다. 확정 전 회의안이면 409 `NOT_CONFIRMED`.
    - 없으면 `topic`이 필요합니다. 시작 시각은 시연 시계의 지금입니다.
    """
    require_member(db, room_id, user_id)

    if body.meeting_id is not None:
        meeting = _meeting(db, room_id, body.meeting_id)
        if meeting.status not in RECORDABLE:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "code": "NOT_CONFIRMED",
                    "message": "아직 확정되지 않은 회의입니다.",
                },
            )
        return meeting_detail(db, meeting)

    if body.topic is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_INPUT",
                "field": "topic",
                "message": "회의 주제를 적어 주세요.",
            },
        )
    now = demo_clock.now(db)
    meeting = Meeting(
        room_id=room_id,
        topic=body.topic,
        start_at=now,
        end_at=now + ADHOC_MEETING_LENGTH,
        mode=body.mode,
        status=MeetingStatus.CONFIRMED,
        confirmed_at=now,
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return meeting_detail(db, meeting)


@router.get(
    "/meetings/{meeting_id}", response_model=MeetingDetailOut, summary="회의록 보기"
)
def get_meeting(
    room_id: int,
    meeting_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> MeetingDetailOut:
    """원문 + 요약(결정/논의/보류) + 이 회의에서 확정된 할 일 + 확정 전 AI 제안.

    - 요약 전이면 `minutes`가 null입니다. 원문을 먼저 그리고 요약 자리만 비워 두세요.
    - AI 제안은 여기서만 보입니다. 할 일 목록에는 나오지 않습니다.
    """
    require_member(db, room_id, user_id)
    return meeting_detail(db, _meeting(db, room_id, meeting_id))


@router.put(
    "/meetings/{meeting_id}/transcript",
    response_model=MeetingDetailOut,
    summary="직접 쓰기",
)
def write_transcript(
    room_id: int,
    meeting_id: int,
    body: TranscriptIn,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> MeetingDetailOut:
    """원문을 통째로 바꿉니다. 받아적기가 안 될 때 쓰는 길이라 AI를 쓰지 않습니다.

    - 줄마다 한 발언입니다. 빈 줄은 버립니다.
    - `이름: 내용` 꼴이고 이름이 이 방 팀원이면 말한 사람으로 나눕니다. 아니면 말한 사람 없음.
    """
    require_member(db, room_id, user_id)
    meeting = _meeting(db, room_id, meeting_id)

    lines = transcript.parse(body.text, member_names(db, room_id))
    transcript.replace(db, meeting_id, lines)
    meeting.transcript_mode = TranscriptMode.MANUAL
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return meeting_detail(db, meeting)
