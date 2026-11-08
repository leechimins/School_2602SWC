"""Record — 회의록 목록·보기, 기록 시작, 직접 쓰기, 받아적기, 요약·할 일 뽑기. 레인 B.

Swagger 그룹과 파일 이름은 노션 API 명세의 도메인(Record)과 맞춘다. 그룹 이름은 다른 레인처럼 소문자.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session, select

from app.meeting.models import Meeting
from app.minutes import recording, summarize, transcript
from app.minutes import tasks as task_calc
from app.minutes.models import Minutes, TranscriptSegment
from app.minutes.record import (
    RECORDABLE,
    meeting_detail,
    meeting_list,
    member_names,
)
from app.minutes.schemas import (
    MeetingDetailOut,
    MeetingListOut,
    RecordStartIn,
    SegmentsIn,
    SegmentsOut,
    SpeakerMappingIn,
    TranscriptIn,
)
from app.shared import demo_clock
from app.shared.auth import current_user_id, require_member
from app.shared.db import session_dep
from app.shared.enums import (
    MeetingStatus,
    MinutesStatus,
    TranscriptMode,
)

router = APIRouter(prefix="/rooms/{room_id}", tags=["record"])


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


def _recordable_meeting(
    db: Session, room_id: int, meeting_id: int, *, lock: bool = False
) -> Meeting:
    """기록을 붙일 수 있는 회의. 회의안·취소된 회의면 409 `NOT_CONFIRMED`.

    lock이면 행을 잠근 **뒤에** 상태를 본다. 먼저 보고 잠그면 그 사이 취소된
    회의에 받아적기가 붙을 수 있다.
    """
    meeting = _meeting(db, room_id, meeting_id)
    if lock:
        db.refresh(meeting, with_for_update=True)
    if meeting.status not in RECORDABLE:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "NOT_CONFIRMED",
                "message": "아직 확정되지 않은 회의입니다.",
            },
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
    responses={
        200: {"model": MeetingDetailOut, "description": "잡힌 회의에 붙임 (새로 만들지 않음)"},
        201: {"description": "회의를 새로 만들어 기록 시작"},
    },
    summary="회의 기록 시작하기",
)
def start_record(
    room_id: int,
    body: RecordStartIn,
    response: Response,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> MeetingDetailOut:
    """잡힌 회의에 기록을 붙이거나, 잡힌 회의 없이 회의를 새로 만듭니다.

    - `meeting_id`가 있으면 새로 만들지 않고 그 회의를 200으로 돌려줍니다.
      확정 전 회의안이나 취소된 회의면 409 `NOT_CONFIRMED`.
    - 없으면 `topic`이 필요하고 회의를 새로 만들어 201로 돌려줍니다. 시작 시각은 시연 시계의 지금입니다.
    """
    require_member(db, room_id, user_id)

    if body.meeting_id is not None:
        meeting = _recordable_meeting(db, room_id, body.meeting_id)
        response.status_code = status.HTTP_200_OK
        return meeting_detail(db, meeting, user_id)

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
    return meeting_detail(db, meeting, user_id)


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
    return meeting_detail(db, _meeting(db, room_id, meeting_id), user_id)


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
    - 확정 전 회의안이나 취소된 회의면 409 `NOT_CONFIRMED`.
    - 받아적는 중이면 409 `RECORDING`. 멈춘 뒤에는 받아적은 원문을 이걸로 고쳐 쓸 수 있습니다(목소리 라벨은 사라짐).
    """
    require_member(db, room_id, user_id)
    meeting = _locked_recordable(db, room_id, meeting_id)
    recording.reject_while_recording(meeting)

    lines = transcript.parse(body.text, member_names(db, room_id))
    transcript.replace(db, meeting_id, lines)
    meeting.transcript_mode = TranscriptMode.MANUAL
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return meeting_detail(db, meeting, user_id)


# ── 받아적기 ─────────────────────────────────────────────────────────


def _locked_recordable(db: Session, room_id: int, meeting_id: int) -> Meeting:
    """기록을 붙일 수 있는 회의를 잠가서. 두 폰이 동시에 눌러도 한 번만 바뀐다."""
    return _recordable_meeting(db, room_id, meeting_id, lock=True)


@router.post(
    "/meetings/{meeting_id}/recording/start",
    response_model=MeetingDetailOut,
    responses={
        409: {
            "description": "`NOT_CONFIRMED` 확정 전·취소된 회의 / "
            "`TRANSCRIPT_EXISTS` 직접 쓴 원문이 있음 / `RECORDING_STOPPED` 이미 멈춤"
        }
    },
    summary="받아적기 시작",
)
def start_recording(
    room_id: int,
    meeting_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> MeetingDetailOut:
    """이 회의를 받아적기로 기록하기 시작합니다. 시작 시각은 시연 시계의 지금입니다.

    - 받아적는 중에 다시 눌러도 그대로 진행합니다(200, 시작 시각 안 바뀜).
    - 직접 쓴 원문이 이미 있으면 409 `TRANSCRIPT_EXISTS` — 두 원문이 섞이지 않게.
    - 이미 멈춘 받아적기는 다시 시작할 수 없습니다. 409 `RECORDING_STOPPED`.
    - 확정 전 회의안이나 취소된 회의면 409 `NOT_CONFIRMED`.
    - 음성은 서버에 저장하지 않습니다. 받아적은 글은 조각 올리기로 보냅니다.
    """
    require_member(db, room_id, user_id)
    meeting = _locked_recordable(db, room_id, meeting_id)

    current = recording.state(meeting)
    if current == "stopped":
        raise recording.stopped_error()
    if current == "none":
        has_text = db.exec(
            select(TranscriptSegment.id).where(TranscriptSegment.meeting_id == meeting_id)
        ).first()
        if has_text is not None:
            raise recording.conflict("TRANSCRIPT_EXISTS", "이미 직접 쓴 원문이 있어요.")
        meeting.transcript_mode = TranscriptMode.STT
        meeting.recording_started_at = demo_clock.now(db)
        meeting.recording_stopped_at = None
        db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return meeting_detail(db, meeting, user_id)


@router.post(
    "/meetings/{meeting_id}/transcript/segments",
    response_model=SegmentsOut,
    responses={
        409: {"description": "`NOT_RECORDING` 시작 전 / `RECORDING_STOPPED` 멈춘 뒤 / `NOT_CONFIRMED`"}
    },
    summary="받아적은 글 올리기",
)
def add_segments(
    room_id: int,
    meeting_id: int,
    body: SegmentsIn,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> SegmentsOut:
    """받아적은 줄을 번호와 함께 쌓습니다. 끊겼다 다시 보내도 빠짐·중복이 없습니다.

    - 같은 번호를 다시 보내면 건너뜁니다(`skipped`). 처음 온 줄이 남습니다.
    - 응답의 `missing`은 0부터 지금까지 받은 가장 큰 번호 사이에서 아직 안 온 번호입니다. 그것만 다시 보내세요.
    - 순서가 섞여 와도 원문은 언제나 번호 순입니다.
    - 받아적기를 시작하기 전이면 409 `NOT_RECORDING`, 멈춘 뒤면 409 `RECORDING_STOPPED`.
      멈추기 전에 `missing`이 빌 때까지 보내 주세요.
    """
    require_member(db, room_id, user_id)
    meeting = _locked_recordable(db, room_id, meeting_id)
    current = recording.state(meeting)
    if current == "none":
        raise recording.not_recording_error()
    if current == "stopped":
        raise recording.stopped_error()

    stacked = recording.stack(
        db,
        meeting_id,
        [recording.Piece(s.seq, s.speaker_label, s.text) for s in body.segments],
    )
    db.commit()
    return SegmentsOut(
        added=stacked.added,
        skipped=stacked.skipped,
        last_seq=stacked.last_seq,
        missing=stacked.missing,
    )


@router.post(
    "/meetings/{meeting_id}/recording/stop",
    response_model=MeetingDetailOut,
    responses={409: {"description": "`NOT_RECORDING` 시작 전 / `NOT_CONFIRMED`"}},
    summary="받아적기 멈추기",
)
def stop_recording(
    room_id: int,
    meeting_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> MeetingDetailOut:
    """받아적기를 멈춥니다. 쌓인 원문은 그대로 남고, 요약은 요약 API를 따로 불러 주세요.

    - 두 번 눌러도 그대로입니다(200, 멈춘 시각 안 바뀜).
    - 멈춘 뒤에는 조각을 더 받지 않습니다. 멈추기 전에 조각 올리기의 `missing`이 빌 때까지 보내 주세요.
    - 다시 시작할 수 없습니다. 원문을 고치려면 말한 사람 정하기나 직접 쓰기를 쓰세요.
    - 시작 전이면 409 `NOT_RECORDING`.
    """
    require_member(db, room_id, user_id)
    meeting = _locked_recordable(db, room_id, meeting_id)
    current = recording.state(meeting)
    if current == "none":
        raise recording.not_recording_error()
    if current == "recording":
        meeting.recording_stopped_at = demo_clock.now(db)
        db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return meeting_detail(db, meeting, user_id)


@router.put(
    "/meetings/{meeting_id}/speaker-mapping",
    response_model=MeetingDetailOut,
    responses={
        400: {"description": "`INVALID_INPUT` 이 방 팀원이 아님 / 없는 줄 번호"},
        409: {"description": "`RECORDING` 받아적는 중 / `NOT_CONFIRMED`"},
    },
    summary="말한 사람 정하기",
)
def map_speakers(
    room_id: int,
    meeting_id: int,
    body: SpeakerMappingIn,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> MeetingDetailOut:
    """원문의 줄마다 누가 말했는지 정합니다. 받아적기를 멈춘 뒤에 씁니다.

    - `labels`: 목소리 라벨("A")을 팀원에 연결하면 그 라벨의 모든 줄에 한 번에 반영됩니다.
    - `lines`: 줄 번호마다 직접 고릅니다. 같은 요청의 라벨 연결보다 우선합니다. 엔진이 화자를 못 나누면 이것만 씁니다.
    - `null`은 "모름"입니다. 보내지 않은 라벨·줄은 그대로입니다.
    - 정한 뒤 요약을 다시 부르면 바뀐 이름으로 담당자를 추정합니다.
    - 이 방 팀원이 아니거나 없는 줄 번호면 400 `INVALID_INPUT`. 받아적는 중이면 409 `RECORDING`.
    """
    require_member(db, room_id, user_id)
    meeting = _locked_recordable(db, room_id, meeting_id)
    recording.reject_while_recording(meeting)

    members = {u.id for u in task_calc.members(db, room_id)}
    chosen = {v for v in (*body.labels.values(), *body.lines.values()) if v is not None}
    if not chosen <= members:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_INPUT",
                "field": "speaker_user_id",
                "message": "이 방 팀원만 고를 수 있습니다.",
            },
        )
    seqs = set(
        db.exec(
            select(TranscriptSegment.seq).where(TranscriptSegment.meeting_id == meeting_id)
        ).all()
    )
    if not set(body.lines) <= seqs:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_INPUT", "field": "lines", "message": "그 줄이 없습니다."},
        )

    recording.map_speakers(db, meeting_id, body.labels, body.lines)
    db.commit()
    db.refresh(meeting)
    return meeting_detail(db, meeting, user_id)


@router.post(
    "/meetings/{meeting_id}/summarize",
    response_model=MeetingDetailOut,
    responses={503: {"description": "AI 실패 · 시간 초과. 다시 하기를 보여 주세요"}},
    summary="요약·할 일 뽑기",
)
def summarize_meeting(
    room_id: int,
    meeting_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> MeetingDetailOut:
    """저장된 원문으로 주제 한 줄 · 결정 · 논의 · 보류 · 할 일 제안을 AI로 만듭니다. 최대 20초 걸립니다.

    - 받아적기 정지나 직접 쓰기 저장 뒤에 바로 불러 주세요.
    - 부르자마자 요약 상태가 `summarizing`이 됩니다. 다른 화면은 원문을 먼저 그리고 요약 자리만 비워 두세요.
    - 할 일 제안은 회의록에만 "AI 제안"으로 붙습니다. 확정해야 할 일 목록에 들어갑니다.
    - 담당자는 원문에서 분명할 때만 채워집니다. 기한은 회의 날짜 기준으로 계산합니다.
    - 다시 부르면 요약을 바꾸고, 아직 확정하지 않은 AI 제안을 새 제안으로 바꿉니다. 확정된 할 일과 원문은 그대로입니다.
    - AI가 실패하면 503 `AGENT_TIMEOUT`. 처음이면 요약 상태가 `failed`, 전에 요약이 있었으면 그 요약이 그대로 남습니다.
    - 원문이 없으면 409 `NO_TRANSCRIPT`, 확정 전·취소된 회의면 409 `NOT_CONFIRMED`.
    - 받아적는 중이면 409 `RECORDING`. 멈춘 뒤에 불러 주세요.
    """
    require_member(db, room_id, user_id)
    meeting = _recordable_meeting(db, room_id, meeting_id)
    recording.reject_while_recording(meeting)

    users = task_calc.members(db, room_id)
    names_by_id = {u.id: u.name for u in users if u.id is not None}
    lines = summarize.load_lines(db, meeting_id, names_by_id)
    if not lines:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "NO_TRANSCRIPT", "message": "원문이 없어 정리할 수 없습니다."},
        )

    # 모델을 부르기 전에 "정리 중"을 먼저 커밋한다. 최대 20초 동안 다른
    # 폰에서도 원문과 빈 요약 자리가 보여야 한다.
    minutes = db.exec(select(Minutes).where(Minutes.meeting_id == meeting_id)).first()
    previous = minutes.status if minutes else None
    if minutes is None:
        minutes = Minutes(
            meeting_id=meeting_id,
            headline=meeting.topic[: summarize.MAX_HEADLINE_CHARS],
            status=MinutesStatus.SUMMARIZING,
        )
    minutes.status = MinutesStatus.SUMMARIZING
    db.add(minutes)
    db.commit()

    titles = summarize.confirmed_titles(db, meeting_id)
    prompt = summarize.build_prompt(
        topic=meeting.topic,
        held_on=summarize.held_on(meeting),
        lines=lines,
        member_names=[u.name for u in users],
        confirmed_titles=titles,
    )
    draft = summarize.parse(
        summarize.request(prompt),
        lines=lines,
        names={u.name: u.id for u in users if u.id is not None},
        confirmed_titles=titles,
    )

    if draft is None:
        # 다시 하기가 실패해도 전에 된 요약은 지우지 않는다
        minutes = db.exec(
            select(Minutes).where(Minutes.meeting_id == meeting_id).with_for_update()
        ).one()
        minutes.status = (
            MinutesStatus.DONE if previous == MinutesStatus.DONE else MinutesStatus.FAILED
        )
        db.add(minutes)
        db.commit()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "AGENT_TIMEOUT",
                "message": "정리를 잠시 못 했어요. 잠시 후 다시 해 주세요.",
            },
        )

    summarize.save(db, meeting, draft)
    db.commit()
    db.refresh(meeting)
    return meeting_detail(db, meeting, user_id)
