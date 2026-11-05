"""회의록 · 할 일 제안 · 할 일. 레인 B.

한 방 안의 일이라 prefix가 `/rooms/{room_id}`다.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlmodel import Session, col, func, select

from app.meeting.models import Meeting
from app.minutes import tasks as task_calc
from app.minutes import transcript
from app.minutes.models import Task
from app.minutes.record import (
    RECORDABLE,
    meeting_detail,
    meeting_list,
    member_names,
    tasks_out,
)
from app.minutes.schemas import (
    ConfirmIn,
    ConfirmOut,
    MeetingDetailOut,
    MeetingListOut,
    MyTaskListOut,
    ReassignIn,
    RecordStartIn,
    StatusIn,
    SuggestionOut,
    SuggestionPatch,
    TaskCreateIn,
    TaskListOut,
    TaskOut,
    TaskPatch,
    TranscriptIn,
)
from app.shared import demo_clock
from app.shared.auth import current_user_id, require_member
from app.shared.db import session_dep
from app.shared.enums import MeetingStatus, TaskOrigin, TaskState, TranscriptMode
from app.shared.models import Membership, User

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


# ── Suggest — 확정 전 AI 제안 ────────────────────────────────────────
# 제안은 task 중 confirmed=false인 행이다. 버린 제안은 dropped=true로 남는다.

_ALREADY_CONFIRMED = {
    "code": "ALREADY_CONFIRMED",
    "message": "이미 확정된 할 일입니다.",
}


def _suggestion_not_found() -> HTTPException:
    return HTTPException(
        status.HTTP_404_NOT_FOUND,
        detail={"code": "NOT_FOUND", "message": "그 제안이 없습니다."},
    )


def _suggestion(db: Session, room_id: int, suggestion_id: int) -> Task:
    """이 방의 버리지 않은 제안 하나. 확정 여부는 부르는 쪽이 본다."""
    task = db.exec(
        select(Task)
        .where(
            Task.id == suggestion_id,
            Task.room_id == room_id,
            col(Task.dropped).is_(False),
        )
        .with_for_update()
    ).first()
    if task is None:
        raise _suggestion_not_found()
    return task


def _require_room_member_id(db: Session, room_id: int, user_id: int) -> None:
    """담당자로 고를 수 있는 사람인지. 이 방 팀원만 된다."""
    found = db.exec(
        select(Membership.id).where(
            Membership.room_id == room_id, Membership.user_id == user_id
        )
    ).first()
    if found is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_INPUT",
                "field": "assignee_user_id",
                "message": "이 방의 팀원만 담당자로 고를 수 있습니다.",
            },
        )


def _apply_patch(
    db: Session, room_id: int, task: Task, body: SuggestionPatch | TaskPatch
) -> None:
    """제목·담당자·기한 중 보낸 칸만 바꾼다. 제안 고치기와 할 일 고치기가 같이 쓴다."""
    sent = body.model_fields_set
    if "title" in sent:
        if body.title is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_INPUT",
                    "field": "title",
                    "message": "제목은 비울 수 없습니다.",
                },
            )
        task.title = body.title
    if "assignee_user_id" in sent:
        if body.assignee_user_id is not None:
            _require_room_member_id(db, room_id, body.assignee_user_id)
        task.assignee_user_id = body.assignee_user_id
    if "due_date" in sent:
        task.due_date = body.due_date


@router.post(
    "/suggestions/confirm", response_model=ConfirmOut, summary="제안 확정하기"
)
def confirm_suggestions(
    room_id: int,
    body: ConfirmIn,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> ConfirmOut:
    """AI 제안을 할 일로 확정합니다. 여러 개를 한꺼번에 보낼 수 있습니다.

    - 담당자가 비어 있어도 확정됩니다 ("담당자 없음"으로 들어감).
    - 확정한 사람과 시각이 남습니다. 시각은 시연 시계 기준입니다.
    - 하나라도 이미 확정됐으면 409 `ALREADY_CONFIRMED`이고 아무것도 확정하지 않습니다.
    - 없거나 버렸거나 다른 방의 제안이 섞이면 404 `NOT_FOUND`.
    """
    require_member(db, room_id, user_id)
    ids = list(dict.fromkeys(body.suggestion_ids))

    # 두 사람이 같은 제안을 동시에 누를 수 있다. 행을 잠가서 뒤에 온 쪽이
    # 앞쪽 확정을 본 뒤 409를 받게 한다.
    tasks = db.exec(
        select(Task)
        .where(
            col(Task.id).in_(ids),
            Task.room_id == room_id,
            col(Task.dropped).is_(False),
        )
        .with_for_update()
    ).all()
    if len(tasks) != len(ids):
        raise _suggestion_not_found()
    if any(task.confirmed for task in tasks):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_ALREADY_CONFIRMED)

    now = demo_clock.now(db)
    for task in tasks:
        task.confirmed = True
        task.confirmed_by = user_id
        task.confirmed_at = now
        db.add(task)
    db.commit()
    return ConfirmOut(tasks=tasks_out(db, ids))


@router.patch(
    "/suggestions/{suggestion_id}", response_model=SuggestionOut, summary="제안 고치기"
)
def edit_suggestion(
    room_id: int,
    suggestion_id: int,
    body: SuggestionPatch,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> SuggestionOut:
    """확정 전 제안의 제목·담당자·기한을 고칩니다. 보낸 칸만 바뀝니다.

    - 담당자·기한은 null을 보내면 비웁니다. 제목은 비울 수 없습니다.
    - 담당자는 이 방 팀원만 됩니다.
    - 이미 확정된 할 일이면 409 `ALREADY_CONFIRMED` (할 일 고치기를 쓰세요).
    """
    require_member(db, room_id, user_id)
    task = _suggestion(db, room_id, suggestion_id)
    if task.confirmed:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_ALREADY_CONFIRMED)

    _apply_patch(db, room_id, task, body)
    db.add(task)
    db.commit()
    db.refresh(task)
    assignee = db.get(User, task.assignee_user_id) if task.assignee_user_id else None
    return SuggestionOut(
        id=task.id,
        title=task.title,
        due_date=task.due_date,
        assignee_user_id=task.assignee_user_id,
        assignee_name=assignee.name if assignee else None,
    )


@router.delete(
    "/suggestions/{suggestion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="제안 버리기",
)
def drop_suggestion(
    room_id: int,
    suggestion_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> Response:
    """확정 전 제안을 버립니다. 되돌릴 수 없으므로 화면에서 한 번 더 묻습니다.

    - 행을 지우지 않고 "필요 없음"(`dropped`)으로 둡니다. 회의록에서 빠집니다.
    - 이미 확정된 할 일이면 409 `ALREADY_CONFIRMED` (할 일의 "필요 없음"을 쓰세요).
    """
    require_member(db, room_id, user_id)
    task = _suggestion(db, room_id, suggestion_id)
    if task.confirmed:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_ALREADY_CONFIRMED)

    task.dropped = True
    db.add(task)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Task — 확정된 할 일 ──────────────────────────────────────────────
# 할 일은 task 중 confirmed=true이고 dropped=false인 행이다.


def _task(db: Session, room_id: int, task_id: int) -> Task:
    """이 방의 확정된 할 일 하나. 제안이나 필요 없음은 404.

    상태·내용을 바꾸는 요청이 같이 쓰므로 행을 잠근다. 폰 화면 둘에서
    같은 할 일을 동시에 바꿀 수 있다.
    """
    task = db.exec(
        task_calc.live_tasks(room_id).where(Task.id == task_id).with_for_update()
    ).first()
    if task is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "그 할 일이 없습니다."},
        )
    return task


def _task_out(db: Session, task: Task, viewer_id: int) -> TaskOut:
    return task_calc.task_outs(db, [task], viewer_id)[0]


@router.get("/tasks", response_model=TaskListOut, summary="팀 할 일 보기")
def list_tasks(
    room_id: int,
    state: TaskState | None = Query(default=None, description="이 상태만"),
    assignee_user_id: int | None = Query(default=None, description="이 사람이 담당인 것만"),
    unassigned: bool = Query(default=False, description="true면 담당자 없음만"),
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> TaskListOut:
    """확정된 할 일만. 담당자 없음 → 나 → 다른 사람 순이고 묶음 안은 기한 순입니다.

    - 확정 전 AI 제안은 나오지 않습니다. 대신 `suggestion_count`로 수를 줍니다.
    - "필요 없음"으로 뺀 할 일은 나오지 않습니다.
    """
    require_member(db, room_id, user_id)

    query = task_calc.live_tasks(room_id)
    if state is not None:
        query = query.where(Task.state == state)
    if unassigned:
        query = query.where(col(Task.assignee_user_id).is_(None))
    elif assignee_user_id is not None:
        query = query.where(Task.assignee_user_id == assignee_user_id)
    tasks = task_calc.team_order(list(db.exec(query).all()), user_id)

    suggestion_count = db.exec(
        select(func.count())
        .select_from(Task)
        .where(
            Task.room_id == room_id,
            col(Task.confirmed).is_(False),
            col(Task.dropped).is_(False),
        )
    ).one()
    return TaskListOut(
        tasks=task_calc.task_outs(db, tasks, user_id),
        task_counts=task_calc.task_counts(db, room_id),
        suggestion_count=suggestion_count,
    )


@router.get("/tasks/mine", response_model=MyTaskListOut, summary="내 할 일 보기")
def list_my_tasks(
    room_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> MyTaskListOut:
    """내가 담당인 확정된 할 일. 기한 순이고 기한이 없으면 맨 뒤입니다."""
    require_member(db, room_id, user_id)

    tasks = db.exec(
        task_calc.live_tasks(room_id).where(Task.assignee_user_id == user_id)
    ).all()
    return MyTaskListOut(
        tasks=task_calc.task_outs(db, task_calc.mine_order(list(tasks)), user_id)
    )


@router.post(
    "/tasks",
    response_model=TaskOut,
    status_code=status.HTTP_201_CREATED,
    summary="할 일 직접 추가",
)
def create_task(
    room_id: int,
    body: TaskCreateIn,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> TaskOut:
    """AI 없이 할 일을 바로 만듭니다. 만든 사람이 확정한 사람으로 바로 확정됩니다.

    - 출처 회의가 없어 `source`가 null입니다.
    - 담당자는 이 방 팀원만, 비워도 됩니다.
    """
    require_member(db, room_id, user_id)
    if body.assignee_user_id is not None:
        _require_room_member_id(db, room_id, body.assignee_user_id)

    now = demo_clock.now(db)
    task = Task(
        room_id=room_id,
        title=body.title,
        due_date=body.due_date,
        assignee_user_id=body.assignee_user_id,
        state=TaskState.TODO,
        origin=TaskOrigin.MANUAL,
        confirmed=True,
        confirmed_by=user_id,
        confirmed_at=now,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return _task_out(db, task, user_id)


@router.get("/tasks/{task_id}", response_model=TaskOut, summary="할 일 하나 보기")
def get_task(
    room_id: int,
    task_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> TaskOut:
    """고치기 화면용. 확정 전 제안이나 필요 없음으로 뺀 할 일이면 404."""
    require_member(db, room_id, user_id)
    return _task_out(db, _task(db, room_id, task_id), user_id)


@router.patch(
    "/tasks/{task_id}/status", response_model=TaskOut, summary="할 일 상태 바꾸기"
)
def change_status(
    room_id: int,
    task_id: int,
    body: StatusIn,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> TaskOut:
    """시작 전 · 진행 중 · 막힘 · 완료 사이를 어느 방향으로든 바꿉니다.

    - 담당자만 바꿀 수 있습니다. 아니면 403 `NOT_ASSIGNEE`. 담당자가 없는 할 일은 전원.
    - 지금과 같은 상태를 보내면 아무 일도 일어나지 않습니다.
    """
    require_member(db, room_id, user_id)
    task = _task(db, room_id, task_id)
    if not task_calc.can_change_status(task, user_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "NOT_ASSIGNEE",
                "message": "담당자만 상태를 바꿀 수 있습니다.",
            },
        )

    if task.state != body.state:
        task.state = body.state
        db.add(task)
        db.commit()
        db.refresh(task)
    return _task_out(db, task, user_id)


@router.patch("/tasks/{task_id}", response_model=TaskOut, summary="할 일 내용 고치기")
def edit_task(
    room_id: int,
    task_id: int,
    body: TaskPatch,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> TaskOut:
    """제목·담당자·기한을 고칩니다. 팀원 누구나 됩니다. 보낸 칸만 바뀝니다.

    - 담당자·기한은 null을 보내면 비웁니다. 제목은 비울 수 없습니다.
    - 담당자는 이 방 팀원만 됩니다.
    """
    require_member(db, room_id, user_id)
    task = _task(db, room_id, task_id)
    _apply_patch(db, room_id, task, body)
    db.add(task)
    db.commit()
    db.refresh(task)
    return _task_out(db, task, user_id)


@router.post(
    "/tasks/{task_id}/reassign", response_model=TaskOut, summary="담당자 넘기기"
)
def reassign_task(
    room_id: int,
    task_id: int,
    body: ReassignIn,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> TaskOut:
    """담당자만 바꿉니다. null이면 담당자 없음. 내용 고치기와 같은 규칙입니다."""
    require_member(db, room_id, user_id)
    task = _task(db, room_id, task_id)
    _apply_patch(db, room_id, task, TaskPatch(assignee_user_id=body.assignee_user_id))
    db.add(task)
    db.commit()
    db.refresh(task)
    return _task_out(db, task, user_id)


@router.post(
    "/tasks/{task_id}/dismiss",
    status_code=status.HTTP_204_NO_CONTENT,
    summary='할 일 빼기 ("필요 없음")',
)
def dismiss_task(
    room_id: int,
    task_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> Response:
    """할 일을 "필요 없음"으로 뺍니다. 되돌릴 수 없으므로 화면에서 한 번 더 묻습니다.

    - 팀원 누구나 됩니다. 행을 지우지 않고 목록에서만 빠집니다.
    """
    require_member(db, room_id, user_id)
    task = _task(db, room_id, task_id)
    task.dropped = True
    db.add(task)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
