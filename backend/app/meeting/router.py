"""조율 엔드포인트 — /rooms/{room_id}/schedulings.

지금은 조율을 열고(1~3번) 다시 읽는 둘뿐이다. 라운드를 돌리는 stream·pick·
widen·accept-absent·rerun은 LLM이 붙은 뒤에 여기에 붙는다.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator, Mapping
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from psycopg.errors import UniqueViolation
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, func, select

from app.meeting.models import (
    RUNNING_SCHEDULING_INDEX,
    CandidateSlot,
    Scheduling,
    Utterance,
)
from app.meeting.schemas import SchedulingOut, SchedulingStartIn, UtteranceOut
from app.meeting.agent_loop import member_names, run_rounds
from app.meeting.service import start_scheduling
from app.shared.auth import current_user_id, require_member
from app.shared.db import session_dep
from app.shared.enums import SchedulingStatus
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
                phase=utterance.phase,
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


STEP_SEC = 1.6
"""발언 하나와 다음 발언 사이. 브리프가 전체를 30초 안팎으로 잡았다."""


def _sse(utterance: Utterance, names: Mapping[int, str]) -> str:
    body = UtteranceOut(
        seq=utterance.seq,
        phase=utterance.phase,
        round_no=utterance.round_no,
        speaker_kind=utterance.speaker_kind,
        speaker_user_id=utterance.speaker_user_id,
        # 이름을 채운다. 비워 두면 화면에 "1: 지수는…"처럼 숫자가 나온다.
        speaker_name=names.get(utterance.speaker_user_id or 0),
        text=utterance.text,
        created_at=utterance.created_at,
    )
    return f"data: {body.model_dump_json()}\n\n"


@router.get("/schedulings/{scheduling_id}/stream")
def stream(
    room_id: int,
    scheduling_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> StreamingResponse:
    """발언을 하나씩 흘려보낸다. 이 화면이 시연에서 가장 중요하다.

    스피너를 돌리지 않는다. 브리프: "이 10~20초는 로딩이 아니라 구경거리라서,
    스피너를 돌리면 시연에서 가장 중요한 장면을 덮습니다."

    **라운드를 여기서 직접 돌린다.** 백그라운드 작업을 두지 않는 이유는,
    조율 시작에서 미리 다 돌리면 POST가 10~20초 멈춰 그동안 화면이 비기
    때문이다. 발언이 생기는 대로 흘러가야 쌓이는 것이 보인다.

    두 사람이 같이 열어도 루프는 한 번만 돈다. 맨 앞에서 scheduling 행을
    잠그고, 이미 돈 조율이면 쌓인 발언을 재생한다.
    """
    require_member(db, room_id, user_id)

    # FOR UPDATE. 두 번째 요청은 첫 번째가 상태를 정할 때까지 여기서 기다린다.
    scheduling = db.exec(
        select(Scheduling).where(Scheduling.id == scheduling_id).with_for_update()
    ).first()
    if scheduling is None or scheduling.room_id != room_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "그 조율이 없습니다."},
        )

    # == 로 비교한다. DB에서 읽은 열거값은 str이라 is가 항상 거짓이다
    # (backend/README.md 지킬 것 4번). is를 쓰면 루프가 한 번도 안 돈다.
    names = member_names(db, room_id)
    처음인가 = (
        scheduling.status == SchedulingStatus.RUNNING
        and not scheduling.rounds_used
    )

    def 흘려보내기() -> Iterator[str]:
        if 처음인가:
            for utterance in run_rounds(db, scheduling):
                yield _sse(utterance, names)
                time.sleep(STEP_SEC)
        else:
            # 재진입. 이미 쌓인 것을 같은 속도로 다시 보여 준다.
            쌓인것 = db.exec(
                select(Utterance)
                .where(Utterance.scheduling_id == scheduling_id)
                .order_by(col(Utterance.seq))
            ).all()
            for utterance in 쌓인것:
                yield _sse(utterance, names)
                time.sleep(STEP_SEC)
        # 끝났다는 신호. 화면이 여기서 회의안으로 넘어간다.
        # str()로 감싼다. DB에서 읽은 열거값은 str이라 .value가 없다
        # (backend/README.md 지킬 것 4번). StrEnum이든 str이든 둘 다 된다.
        done = json.dumps({"status": str(scheduling.status)})
        yield f"event: done\ndata: {done}\n\n"

    return StreamingResponse(
        흘려보내기(),
        media_type="text/event-stream",
        # 프록시가 버퍼링하면 발언이 한꺼번에 쏟아진다.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
