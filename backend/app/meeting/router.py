"""조율·회의·일정 엔드포인트 — /rooms/{room_id} 아래.

세 묶음이 있다.

조율    POST /schedulings, GET /schedulings/{id}, GET /schedulings/{id}/stream
회의  GET /proposals/{id}, POST /proposals/{id}/respond
일정    GET /schedule

pick은 없앴다(11/5) — 사람이 후보를 고르는 단계가 없어졌다. widen도 없앴다
(11/7) — 새 기간으로 조율을 다시 열면 된다. rerun은 아직 없다. 한 파일에 둔 이유는 셋이 같은 네 테이블(scheduling,
candidate_slot, meeting, meeting_response)을 보고 같은 약속 하나를 지켜야
하기 때문이다: **남의 불편 점수는 응답에 담지 않는다**(명세 권장 규칙 3).
나눠 두면 한쪽만 burden()을 거쳐 내보내는 일이 생긴다.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from psycopg.errors import UniqueViolation
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, func, select

from app.meeting.models import (
    RUNNING_SCHEDULING_INDEX,
    CandidateSlot,
    Meeting,
    MeetingResponse,
    Scheduling,
    SlotCost,
    Utterance,
)
from app.meeting.schemas import (
    CoordinatingBrief,
    MeetingBrief,
    ProposalOut,
    ResponderOut,
    RespondIn,
    RespondOut,
    ScheduleOut,
    SchedulingOut,
    SchedulingStartIn,
    UtteranceOut,
)
from app.meeting import rerun, runner
from app.meeting.agent_loop import award_yield, member_names, yield_totals
from app.meeting.scorer import yield_points
from app.meeting.service import burden, start_scheduling
from app.room.service import yield_level
from app.shared import demo_clock
from app.shared.auth import current_user_id, require_member
from app.shared.db import session_dep
from app.shared.enums import (
    MeetingStatus,
    NotificationKind,
    ResponseState,
    SchedulingStatus,
)
from app.shared.models import Room, User
from app.shared.notify import emit

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


def _awaiting_response(db: Session, room_id: int) -> bool:
    """아직 안 지난 회의 중 수락 대기(proposed)가 있는지.

    shortcut: 누가 영영 안 답하면 그 회의가 끝나는 시각까지 새 조율을 못
    연다. 지난 회의는 세지 않으므로 그 뒤에는 풀린다. 팀장이 직접 거절하면
    (예산이 남을 때) 다시 조율로 넘어가니 시연에서는 막히지 않는다. 팀장이
    회의를 취소하는 길이 필요해지면 그때 더한다.
    """
    return (
        db.exec(
            select(Meeting.id).where(
                Meeting.room_id == room_id,
                Meeting.status == MeetingStatus.PROPOSED,
                Meeting.end_at >= demo_clock.now(db),
            )
        ).first()
        is not None
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

    # 수락을 기다리는 회의가 있는 동안은 새 조율을 열 수 없다. 열면 같은 시간이
    # 후보로 또 나올 수 있고, 거절로 옛 조율을 되살릴 때 "한 방에 running 하나"
    # 제약과 부딪친다.
    if _awaiting_response(db, room_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "AWAITING_RESPONSE",
                "message": "수락을 기다리는 회의가 있어요. 모두 답한 뒤에 다시 시작해 주세요.",
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

    # 라운드를 뒷단에서 돌리기 시작한다. 여기서 다 돌리면 POST가 10~20초
    # 멈춰 그동안 화면이 빈다. 스트림은 쌓이는 발언을 따라 읽기만 한다.
    #
    # 후보가 하나도 없어 failed로 끝난 조율은 돌릴 것이 없다.
    if scheduling.status == SchedulingStatus.RUNNING:
        assert scheduling.id is not None
        runner.start(scheduling.id)

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

STALL_SEC = 40.0
"""새 발언 없이 이만큼 지나면 스트림을 닫는다.

바닥값이다. 라운드를 돌리는 쪽이 터지면 runner가 상태를 failed로 떨구므로
보통은 여기까지 안 온다. 서버 프로세스가 통째로 죽은 경우에만 걸린다.

LLM 타임아웃이 20초(shared/llm.py)라 한 라운드의 공백이 그만큼 길 수 있다.
두 배로 잡아 멀쩡한 조율을 끊지 않는다.
"""


def _sse(utterance: Utterance, names: Mapping[int, str]) -> str:
    body = UtteranceOut(
        seq=utterance.seq,
        round_no=utterance.round_no,
        speaker_kind=utterance.speaker_kind,
        speaker_user_id=utterance.speaker_user_id,
        # 이름을 채운다. 비워 두면 화면에 "1: 지수는…"처럼 숫자가 나온다.
        speaker_name=names.get(utterance.speaker_user_id or 0),
        text=utterance.text,
        created_at=utterance.created_at,
    )
    return f"data: {body.model_dump_json()}\n\n"


def _status(db: Session, scheduling_id: int) -> SchedulingStatus:
    """지금 상태를 DB에서 다시 읽는다.

    스칼라로 읽는 이유: 라운드는 **다른 세션**(runner의 스레드)이 바꾼다.
    이미 읽어 둔 Scheduling 객체를 다시 보면 세션이 캐시한 옛 값이 나와,
    스트림이 끝난 조율을 영영 "도는 중"으로 본다.
    """
    return db.exec(
        select(Scheduling.status).where(Scheduling.id == scheduling_id)  # type: ignore[arg-type]
    ).one()


@router.get("/schedulings/{scheduling_id}/stream")
def stream(
    room_id: int,
    scheduling_id: int,
    after: int = 0,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> StreamingResponse:
    """쌓이는 발언을 따라 읽어 흘려보낸다. 이 화면이 시연에서 가장 중요하다.

    스피너를 돌리지 않는다. 브리프: "이 10~20초는 로딩이 아니라 구경거리라서,
    스피너를 돌리면 시연에서 가장 중요한 장면을 덮습니다."

    **여기서 라운드를 돌리지 않는다.** 돌리는 쪽은 meeting/runner.py이고
    조율 시작(POST)이 띄운다. 전에는 이 응답 안에서 돌렸는데, 그러면 조율
    전체가 보는 사람 한 명의 연결에 묶인다 — 두 번째로 연 사람은 그때까지
    쌓인 것만 보고 끝났고, 탭을 닫으면 조율이 거기서 멈췄다.

    읽기만 하므로 갈래가 하나다. 늦게 열어도 **처음부터** 같은 속도로
    보고, 아직 도는 중이면 새 발언이 나오는 대로 이어 본다. 몇 명이 같이
    열어도 서로 아무 영향이 없다.

    after는 "이 번호까지는 이미 봤다"이다. 거절로 조율이 다시 돌 때 화면이
    옛 대화를 또 재생하지 않고 새 발언만 받게 한다.
    """
    require_member(db, room_id, user_id)

    scheduling = db.get(Scheduling, scheduling_id)
    if scheduling is None or scheduling.room_id != room_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "그 조율이 없습니다."},
        )
    names = member_names(db, room_id)

    def 흘려보내기() -> Iterator[str]:
        마지막seq = max(after, 0)
        마지막으로본것 = time.monotonic()
        while True:
            # **상태를 발언보다 먼저 읽는다.** 반대로 읽으면 그 사이에 조율이
            # 끝났을 때 마지막 발언 몇 개를 놓치고 닫는다. 발언은 상태를 바꾸기
            # 전에 커밋되므로, 끝난 상태를 먼저 봤다면 그 발언은 이미 다 있다.
            상태 = _status(db, scheduling_id)
            새것 = db.exec(
                select(Utterance)
                .where(
                    Utterance.scheduling_id == scheduling_id,
                    col(Utterance.seq) > 마지막seq,
                )
                .order_by(col(Utterance.seq))
            ).all()
            for utterance in 새것:
                yield _sse(utterance, names)
                마지막seq = utterance.seq
                time.sleep(STEP_SEC)
            if 새것:
                마지막으로본것 = time.monotonic()

            # 끝난 조율이어도 위에서 남은 발언을 다 보낸 뒤라 빠뜨리지 않는다.
            if 상태 != SchedulingStatus.RUNNING:
                break
            if time.monotonic() - 마지막으로본것 > STALL_SEC:
                # 돌리던 쪽이 상태도 못 남기고 죽었다. 영원히 붙잡지 않는다.
                break
            time.sleep(STEP_SEC)

        # 끝났다는 신호. 화면이 여기서 회의로 넘어간다.
        # str()로 감싼다. DB에서 읽은 열거값은 str이라 .value가 없다
        # (backend/README.md 지킬 것 4번). StrEnum이든 str이든 둘 다 된다.
        done = json.dumps({"status": str(상태)})
        yield f"event: done\ndata: {done}\n\n"

    return StreamingResponse(
        흘려보내기(),
        media_type="text/event-stream",
        # 프록시가 버퍼링하면 발언이 한꺼번에 쏟아진다.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 회의 ──────────────────────────────────────────────────────────


def _meeting(db: Session, room_id: int, meeting_id: int, lock: bool = False) -> Meeting:
    """회의 한 행. lock이면 FOR UPDATE로 잠근다.

    방까지 맞는지 본다. 안 보면 다른 방의 회의를 id만 바꿔 열 수 있다.
    """
    statement = select(Meeting).where(Meeting.id == meeting_id)
    if lock:
        statement = statement.with_for_update()
    meeting = db.exec(statement).first()
    if meeting is None or meeting.room_id != room_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "그 회의가 없습니다."},
        )
    return meeting


def _slot_costs(db: Session, candidate_slot_id: int | None) -> list[SlotCost]:
    """회의가 나온 후보의 사람별 불편. 조율 없이 만든 회의면 빈 목록이다."""
    if candidate_slot_id is None:
        return []
    return list(
        db.exec(
            select(SlotCost).where(SlotCost.candidate_slot_id == candidate_slot_id)
        ).all()
    )


def _count(responses: Sequence[MeetingResponse], state: ResponseState) -> int:
    return sum(1 for r in responses if r.state == state)


@router.get("/proposals/{meeting_id}", response_model=ProposalOut)
def read_proposal(
    room_id: int,
    meeting_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> ProposalOut:
    """회의 하나. "회의 일정 조율 확인" 화면이 이걸로 그려진다.

    **보는 사람마다 내용이 다르다.** my_score는 요청한 사람 것이고, 남의
    점수는 burden 세 단계로만 나간다(명세 권장 규칙 3).
    """
    require_member(db, room_id, user_id)
    meeting = _meeting(db, room_id, meeting_id)

    costs = {c.user_id: c for c in _slot_costs(db, meeting.candidate_slot_id)}
    names = member_names(db, room_id)
    totals = yield_totals(db, room_id)
    responses = db.exec(
        select(MeetingResponse)
        .where(MeetingResponse.meeting_id == meeting_id)
        .order_by(col(MeetingResponse.id))
    ).all()

    responders: list[ResponderOut] = []
    for response in responses:
        cost = costs.get(response.user_id)
        # 점수가 없으면(조율 없이 만든 회의) 괜찮음으로 둔다. 빈 칸을 보여
        # 주는 것보다 낫고, 숫자를 지어내지도 않는다.
        score = cost.score if cost else 1
        responders.append(
            ResponderOut(
                user_id=response.user_id,
                name=names.get(response.user_id, ""),
                state=response.state,
                burden=burden(score),
                reason=cost.reason if cost else "",
                yield_level=yield_level(totals.get(response.user_id, 0)),
                feedback=response.feedback,
                responded_at=response.responded_at,
            )
        )

    mine = next((r for r in responses if r.user_id == user_id), None)
    my_cost = costs.get(user_id)
    scheduling = (
        db.get(Scheduling, meeting.scheduling_id)
        if meeting.scheduling_id is not None
        else None
    )

    return ProposalOut(
        id=meeting_id,
        topic=meeting.topic,
        start_at=meeting.start_at,
        end_at=meeting.end_at,
        mode=meeting.mode,
        status=meeting.status,
        rationale=meeting.rationale,
        scheduling_status=scheduling.status if scheduling else None,
        my_score=my_cost.score if my_cost else None,
        my_reason=my_cost.reason if my_cost else "",
        my_yield_points=(
            yield_points(my_cost.score, my_cost.available) if my_cost else 0
        ),
        my_state=mine.state if mine else None,
        can_respond=(
            mine is not None
            and meeting.status == MeetingStatus.PROPOSED
            and mine.state == ResponseState.PENDING
        ),
        # 이미 확정된 회의에는 피드백만 남긴다. 조정으로 확정된 안이 주로 이
        # 길로 온다(브리프 11/5) — 전원 수락으로 확정된 회의도 같다.
        feedback_only=mine is not None and meeting.status == MeetingStatus.CONFIRMED,
        responders=responders,
    )


@router.post("/proposals/{meeting_id}/respond", response_model=RespondOut)
def respond(
    room_id: int,
    meeting_id: int,
    body: RespondIn,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> RespondOut:
    """수락·거절. 전원이 수락하면 **이 요청 안에서 확정된다.**

    확정 버튼이 없다(브리프). 마지막으로 수락한 사람의 이 요청이 유일한
    기회라서, 상태·확정 시각·양보 장부·합계·알림이 한 트랜잭션에 들어간다.

    맨 앞에서 meeting 행을 FOR UPDATE로 잠근다. 안 잠그면 마지막 두 사람이
    같은 순간에 누를 때 둘 다 "아직 한 명 남았다"를 읽어 아무도 확정하지
    않거나, 둘 다 확정해서 양보 점수가 두 번 들어간다. 시연이 한 창에 폰
    화면 둘을 띄우는 구조라 실제로 일어난다.

    **거절하면 라운드 예산이 남았을 때 바로 다시 조율한다**(meeting/rerun.py).
    옛 회의는 cancelled가 되고 조율이 다시 running으로 돈다. 예산이 0이면
    다시 돌지 않고, 거절한 사람을 불참으로 둔 채 나머지가 모두 수락하면
    회의가 선다.
    """
    require_member(db, room_id, user_id)
    meeting = _meeting(db, room_id, meeting_id, lock=True)

    mine = db.exec(
        select(MeetingResponse).where(
            MeetingResponse.meeting_id == meeting_id,
            MeetingResponse.user_id == user_id,
        )
    ).first()
    if mine is None:
        # 1명 불참안에서 빠지는 사람이다. 안 오는 회의를 수락·거절할 자리는
        # 없다(브리프: "빠지는 사람은 응답자에서 빠지고").
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN",
                "message": "이 회의에 답할 사람이 아닙니다.",
            },
        )

    now = demo_clock.now(db)
    siblings = db.exec(
        select(MeetingResponse).where(MeetingResponse.meeting_id == meeting_id)
    ).all()

    if meeting.status == MeetingStatus.CONFIRMED:
        # 이미 확정됐다. 피드백만 받는다(브리프 11/5의 B안). accept는 보지
        # 않는다 — 확정된 회의를 뒤집는 길이 아니다. 조정으로 확정된 안이
        # 주로 이 길로 오고, 그때 내 state는 accepted로 깔려 있다.
        mine.feedback = body.feedback
        if mine.responded_at is None:
            mine.responded_at = now
        db.add(mine)
        db.commit()
        return RespondOut(
            meeting_id=meeting_id,
            my_state=mine.state,
            meeting_status=MeetingStatus.CONFIRMED,
            pending_count=_count(siblings, ResponseState.PENDING),
            declined_count=_count(siblings, ResponseState.DECLINED),
            feedback_only=True,
        )

    if meeting.status != MeetingStatus.PROPOSED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "CLOSED", "message": "끝난 회의입니다."},
        )

    mine.state = ResponseState.ACCEPTED if body.accept else ResponseState.DECLINED
    mine.feedback = body.feedback
    mine.responded_at = now
    db.add(mine)
    db.flush()  # siblings에 내 새 상태가 보이게.

    # 거절이고 라운드 예산이 남았으면 **바로 다시 조율한다**(브리프 11/5).
    # 다른 사람의 답을 기다리지 않는다 — 한 명이 거절한 회의는 어차피 못 선다.
    if not body.accept:
        scheduling = (
            db.get(Scheduling, meeting.scheduling_id)
            if meeting.scheduling_id is not None
            else None
        )
        if scheduling is not None and rerun.can_rerun(scheduling):
            남은 = rerun.rounds_left(scheduling)
            조율 = scheduling.id
            assert 조율 is not None
            rerun.reopen(db, scheduling, meeting, user_id)
            try:
                db.commit()
            except IntegrityError as exc:
                # 그 사이에 팀장이 새 조율을 열었다. start가 수락 대기 중이면
                # 막지만, 두 요청이 같은 순간이면 이 제약이 마지막 방어선이다.
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
            # 커밋 뒤에 띄운다. 뒷단 루프가 취소·재개된 상태를 읽어야 한다.
            runner.start(조율)
            return RespondOut(
                meeting_id=meeting_id,
                my_state=ResponseState.DECLINED,
                meeting_status=MeetingStatus.CANCELLED,
                pending_count=_count(siblings, ResponseState.PENDING),
                declined_count=_count(siblings, ResponseState.DECLINED),
                rerun=True,
                rounds_left=남은,
            )

    # 예산이 없어서 다시 조율하지 못한 거절은 그 사람을 **불참으로 두고**
    # 나머지가 모두 수락하면 회의가 선다(브리프 11/5). 거절한 사람은 참석
    # 대상이 아니다.
    참석 = [s for s in siblings if s.state != ResponseState.DECLINED]
    확정됐나 = bool(참석) and all(s.state == ResponseState.ACCEPTED for s in 참석)
    if 확정됐나:
        meeting.status = MeetingStatus.CONFIRMED
        meeting.confirmed_at = now
        db.add(meeting)
        # 양보 점수는 **와 주는 사람만** 받는다. 거절한 사람은 맞춰 준 게 아니다.
        수락자 = {s.user_id for s in 참석}
        award_yield(
            db,
            room_id,
            meeting_id,
            [c for c in _slot_costs(db, meeting.candidate_slot_id) if c.user_id in 수락자],
        )
        이름 = member_names(db, room_id)
        빠진 = [이름.get(s.user_id, "팀원") for s in siblings if s.state == ResponseState.DECLINED]
        emit(
            db,
            room_id=room_id,
            user_ids=[s.user_id for s in siblings],
            kind=NotificationKind.MEETING_CONFIRMED,
            reason=(
                f"{meeting.topic} 회의가 확정됐습니다."
                + (f" {', '.join(빠진)} 님은 빠져요." if 빠진 else "")
            )[:200],
            dedupe=f"meeting{meeting_id}",
            meeting_id=meeting_id,
        )
    db.commit()

    return RespondOut(
        meeting_id=meeting_id,
        my_state=mine.state,
        meeting_status=meeting.status,
        confirmed_now=확정됐나,
        pending_count=_count(siblings, ResponseState.PENDING),
        declined_count=_count(siblings, ResponseState.DECLINED),
    )


# ── 일정 보기 ───────────────────────────────────────────────────────


@router.get("/schedule", response_model=ScheduleOut)
def schedule(
    room_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> ScheduleOut:
    """일정 보기(회의 관리) 한 화면. 브리프 순서 그대로다.

    조율 중인 회의 → 잡힌 회의 → 지난 회의. 받아적기 버튼은 잡힌 회의 각
    줄에 프론트가 붙인다(B 레인).

    지난 것과 다가오는 것을 **서버가** 가른다. 기준은 시연 시계다 —
    프론트가 자기 시계로 가르면 시연에서 날짜를 앞으로 옮겼을 때 서버가
    보내는 목록과 화면이 어긋난다.
    """
    require_member(db, room_id, user_id)
    now = demo_clock.now(db)

    coordinating = [
        CoordinatingBrief(
            id=s.id or 0,
            topic=s.topic,
            window_start=s.window_start,
            window_end=s.window_end,
            status=s.status,
        )
        for s in db.exec(
            select(Scheduling)
            .where(
                Scheduling.room_id == room_id,
                Scheduling.status == SchedulingStatus.RUNNING,
            )
            .order_by(col(Scheduling.created_at))
        ).all()
    ]

    # 취소된 회의는 어느 칸에도 넣지 않는다. 브리프의 세 묶음에 자리가 없다.
    meetings = db.exec(
        select(Meeting)
        .where(
            Meeting.room_id == room_id,
            col(Meeting.status).in_(
                [MeetingStatus.PROPOSED, MeetingStatus.CONFIRMED, MeetingStatus.DONE]
            ),
        )
        .order_by(col(Meeting.start_at))
    ).all()
    ids = [m.id for m in meetings if m.id is not None]

    내응답: dict[int, ResponseState] = {}
    대기수: dict[int, int] = {}
    if ids:
        for response in db.exec(
            select(MeetingResponse).where(col(MeetingResponse.meeting_id).in_(ids))
        ).all():
            if response.user_id == user_id:
                내응답[response.meeting_id] = response.state
            if response.state == ResponseState.PENDING:
                대기수[response.meeting_id] = 대기수.get(response.meeting_id, 0) + 1

    # 조정으로 정해진 회의인가. 화면이 "확정 · 조정"으로 그린다.
    조정된조율 = {
        s.id
        for s in db.exec(
            select(Scheduling).where(
                Scheduling.room_id == room_id,
                Scheduling.status == SchedulingStatus.SETTLED,
            )
        ).all()
    }

    upcoming: list[MeetingBrief] = []
    past: list[MeetingBrief] = []
    for meeting in meetings:
        brief = MeetingBrief(
            id=meeting.id or 0,
            topic=meeting.topic,
            start_at=meeting.start_at,
            end_at=meeting.end_at,
            mode=meeting.mode,
            status=meeting.status,
            settled=meeting.scheduling_id in 조정된조율,
            my_state=내응답.get(meeting.id or 0),
            pending_count=대기수.get(meeting.id or 0, 0),
        )
        # 끝난 시각으로 가른다. 회의 중인 것은 아직 다가오는 것에 둔다 —
        # 받아적기 버튼이 거기 붙는다.
        지났나 = meeting.end_at < now or meeting.status == MeetingStatus.DONE
        (past if 지났나 else upcoming).append(brief)

    past.reverse()  # 최근 것이 위로.
    return ScheduleOut(coordinating=coordinating, upcoming=upcoming, past=past)
