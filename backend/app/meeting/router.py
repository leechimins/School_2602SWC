"""조율 엔드포인트 — /rooms/{room_id}/schedulings.

지금은 조율을 열고(1~3번) 다시 읽는 둘뿐이다. 라운드를 돌리는 stream·pick·
widen·accept-absent·rerun은 LLM이 붙은 뒤에 여기에 붙는다.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.errors import UniqueViolation
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, func, select

from app.meeting.models import (
    RUNNING_SCHEDULING_INDEX,
    CandidateSlot,
    Scheduling,
    Utterance,
)
from app.meeting.schemas import SchedulingOut, SchedulingStartIn, UtteranceOut
from app.meeting.service import start_scheduling
from app.shared.auth import current_user_id, require_member
from app.shared.db import session_dep
from app.shared.models import Room, User

router = APIRouter(prefix="/rooms/{room_id}", tags=["meeting"])


def _room(db: Session, room_id: int) -> Room:
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "그 방이 없습니다."},
        )
    return room


def _is_running_conflict(exc: IntegrityError) -> bool:
    """"이미 도는 조율이 있다"로 깨진 것인지.

    psycopg가 Postgres의 진단 정보를 그대로 넘겨 준다. diag.constraint_name이
    깨진 제약의 이름이다 — 에러 문장을 뒤지지 않아도 된다.
    """
    orig = exc.orig
    if not isinstance(orig, UniqueViolation):
        return False
    return orig.diag.constraint_name == RUNNING_SCHEDULING_INDEX


def _require_offset(moment: datetime, field: str) -> None:
    """오프셋 없는 시각은 받지 않는다. 명세 권장 규칙 2다.

    받아 주면 조용히 틀린다. naive datetime에 astimezone(KST)를 부르면
    **서버의 시간대**를 기준으로 해석하므로, 배포 서버가 UTC면 팀장이 보낸
    오전 9시가 오후 6시가 된다. 후보 격자 전체가 아홉 시간 밀린다.

    shared/demo_clock.set_clock()이 같은 이유로 같은 검사를 한다.
    """
    if moment.tzinfo is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_INPUT",
                "field": field,
                "message": "시각에 +09:00을 붙여 보내 주세요.",
            },
        )


def _to_out(db: Session, scheduling: Scheduling) -> SchedulingOut:
    assert scheduling.id is not None
    count = db.exec(
        select(func.count())
        .select_from(CandidateSlot)
        .where(CandidateSlot.scheduling_id == scheduling.id)
    ).one()

    rows = db.exec(
        select(Utterance, User.name)
        .join(User, User.id == Utterance.speaker_user_id, isouter=True)
        .where(Utterance.scheduling_id == scheduling.id)
        .order_by(Utterance.seq)
    ).all()

    return SchedulingOut(
        id=scheduling.id,
        topic=scheduling.topic,
        window_start=scheduling.window_start,
        window_end=scheduling.window_end,
        duration_min=scheduling.duration_min,
        mode=scheduling.mode,
        status=scheduling.status,
        rounds_used=scheduling.rounds_used,
        candidate_count=count,
        utterances=[
            UtteranceOut(
                seq=utterance.seq,
                round_no=utterance.round_no,
                speaker_kind=utterance.speaker_kind,
                speaker_user_id=utterance.speaker_user_id,
                speaker_name=name,
                text=utterance.text,
                created_at=utterance.created_at,
            )
            for utterance, name in rows
        ],
    )


@router.post(
    "/schedulings", response_model=SchedulingOut, status_code=status.HTTP_201_CREATED
)
def start(
    room_id: int,
    body: SchedulingStartIn,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> SchedulingOut:
    """조율 시작. 팀장만.

    브리프: "방 생성하기와 조율 시작은 팀장만 합니다." 팀장인지는
    room.leader_user_id 하나로 본다 — membership에 role 열이 없다.
    """
    room = _room(db, room_id)
    if room.leader_user_id != user_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "조율은 팀장만 시작할 수 있습니다."},
        )
    _require_offset(body.window_start, "window_start")
    _require_offset(body.window_end, "window_end")
    if body.window_start >= body.window_end:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_INPUT",
                "field": "window_start",
                "message": "시작일이 마감일보다 앞이어야 합니다.",
            },
        )

    try:
        scheduling = start_scheduling(db, room_id, user_id, body)
    except IntegrityError as exc:
        # 한 방에 도는 조율은 하나뿐이다(부분 유니크 인덱스). 조율이 도는
        # 중에 팀장이 한 번 더 누르는 일은 쉽게 일어나고, 그러면 발언이 두
        # 줄기로 섞여 가장 중요한 화면이 망가진다.
        #
        # 어느 제약이 깨졌는지는 Postgres가 알려 주는 제약 이름으로 판단한다.
        # 에러 문장 속 글자를 찾는 쪽은 인덱스 이름을 바꾸면 조용히 어긋나고,
        # 그러면 이 상황이 409 대신 500으로 나간다. 조율 시작이 깨뜨릴 수 있는
        # 제약은 이것 말고도 ck_slot_cost_score·ck_candidate_round가 있는데,
        # 그건 우리 버그라서 500이 맞다.
        db.rollback()
        if not _is_running_conflict(exc):
            raise
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "ALREADY_RUNNING",
                "message": "이미 진행 중인 조율이 있습니다.",
            },
        ) from exc

    return _to_out(db, scheduling)


@router.get("/schedulings/{scheduling_id}", response_model=SchedulingOut)
def read(
    room_id: int,
    scheduling_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> SchedulingOut:
    """지금까지의 조율. 재진입용이라 쌓인 발언을 한 번에 준다.

    SSE가 끊겼다 들어와도 처음부터 다시 볼 수 있어야 한다 — 이 화면이
    시연에서 가장 중요한 장면이다.
    """
    require_member(db, room_id, user_id)
    scheduling = db.get(Scheduling, scheduling_id)
    if scheduling is None or scheduling.room_id != room_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "그 조율이 없습니다."},
        )
    return _to_out(db, scheduling)
