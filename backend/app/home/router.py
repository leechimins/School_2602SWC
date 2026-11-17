"""홈 — GET /rooms/{room_id}/home.

앱을 열면 처음 보는 화면이고, 네 곳에서 재료를 모은다: 방(기간), 조율과
회의, 알림, 할 일. 그래서 어느 도메인에도 안 들어가고 자기 모듈을 갖는다.

**레인 B의 task를 읽는다.** 쓰지는 않는다 — 브리프가 "my_tasks는 B
데이터"라고 적었고, 홈이 그걸 보여 주는 화면이라 읽기는 피할 수 없다.
room/router.py에 끼워 넣지 않은 것도 같은 이유다. 그 파일은 레인 B 것이고,
한 파일을 둘이 고치면 병합이 엉킨다.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, col, func, select

from app.home import auto
from app.home.suggest import suggest
from app.home.schemas import (
    AgentSettingIn,
    AgentSettingOut,
    Coordinating,
    HomeOut,
    MyTask,
    NextMeeting,
    TaskBucket,
)
from app.meeting.models import Meeting, MeetingResponse, Scheduling
from app.minutes.models import Task
from app.minutes.record import finished_ids
from app.notice.models import AgentLog, Notification
from app.notice.router import AgentLogOut
from app.shared import demo_clock
from app.shared.auth import current_user_id, require_member
from app.shared.db import session_dep
from app.shared.enums import MeetingStatus, ResponseState, SchedulingStatus, TaskState
from app.shared.models import Membership, Room

router = APIRouter(prefix="/rooms/{room_id}", tags=["home"])


@router.get("/home", response_model=HomeOut)
def read_home(
    room_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> HomeOut:
    """홈 한 화면. 디데이, 다음 회의 하나, 내 할 일, 안 읽은 알림 수."""
    require_member(db, room_id, user_id)
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "그 방이 없습니다."},
        )

    # 시연 시계다. real_now()가 아니다 — 시연에서 날짜를 앞으로 옮겨
    # 디데이와 늦음 뱃지를 보여 준다.
    now = demo_clock.now(db)
    today = now.date()
    leader = room.leader_user_id == user_id
    # 맡겨 뒀으면 여기서 스스로 조율을 연다. 아래 coordinating이 바로 그걸 보여 준다.
    auto.maybe_start(db, room, now)

    return HomeOut(
        today=today,
        start_date=room.start_date,
        due_date=room.due_date,
        d_day=(room.due_date - today).days,
        next_meeting=_next_meeting(db, room_id, user_id),
        coordinating=_coordinating(db, room_id),
        my_tasks=_my_tasks(db, room_id, user_id, today),
        unread_notifications=_unread(db, room_id, user_id),
        can_start_scheduling=leader,
        suggestion=suggest(db, room, now) if leader else None,
        auto_schedule=auto.auto_on(db, room_id),
        agent_log=_recent_log(db, room_id),
        invite_code=room.invite_code,
        joined_count=_joined(db, room_id),
        member_count=room.member_count,
    )


@router.put("/agent-setting", response_model=AgentSettingOut)
def put_agent_setting(
    room_id: int,
    body: AgentSettingIn,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> AgentSettingOut:
    """에이전트에게 조율 시작을 맡기거나 거둔다. 팀장만 — 조율 시작이 팀장 권한이다."""
    require_member(db, room_id, user_id)
    room = db.get(Room, room_id)
    if room is None or room.leader_user_id != user_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "조율 맡기기는 팀장만 바꿀 수 있습니다."},
        )
    auto.set_auto(db, room_id, body.auto_schedule)
    return AgentSettingOut(auto_schedule=body.auto_schedule)


RECENT_LOG = 3


def _recent_log(db: Session, room_id: int) -> list[AgentLogOut]:
    """에이전트가 한 일 최근 몇 줄. 홈에서 에이전트가 혼자 일하고 있음이 보이게."""
    logs = db.exec(
        select(AgentLog)
        .where(AgentLog.room_id == room_id)
        .order_by(col(AgentLog.created_at).desc(), col(AgentLog.id).desc())
        .limit(RECENT_LOG)
    ).all()
    return [AgentLogOut(id=l.id, at=l.created_at, what=l.what, why=l.why) for l in logs]  # type: ignore[arg-type]


def _next_meeting(db: Session, room_id: int, user_id: int) -> NextMeeting | None:
    """아직 안 지난 회의 중 가장 이른 것 하나.

    확정 대기(proposed)도 보여 준다. 아직 확정이 아니어도 다음에 있을 일이고,
    홈에서 응답을 재촉하는 자리이기도 하다. 끝 시각 전이라도 기록을 마친 회의는 뺀다.
    """
    now = demo_clock.now(db)
    candidates = list(
        db.exec(
            select(Meeting)
            .where(
                Meeting.room_id == room_id,
                col(Meeting.status).in_([MeetingStatus.PROPOSED, MeetingStatus.CONFIRMED]),
                Meeting.end_at >= now,
            )
            .order_by(col(Meeting.start_at))
        ).all()
    )
    finished = finished_ids(db, candidates)
    meeting = next((m for m in candidates if m.id not in finished), None)
    if meeting is None or meeting.id is None:
        return None

    responses = db.exec(
        select(MeetingResponse).where(MeetingResponse.meeting_id == meeting.id)
    ).all()
    mine = next((r for r in responses if r.user_id == user_id), None)

    settled = False
    if meeting.scheduling_id is not None:
        scheduling = db.get(Scheduling, meeting.scheduling_id)
        settled = scheduling is not None and (
            scheduling.status == SchedulingStatus.SETTLED
        )

    return NextMeeting(
        id=meeting.id,
        topic=meeting.topic,
        start_at=meeting.start_at,
        end_at=meeting.end_at,
        mode=str(meeting.mode),
        status=meeting.status,
        settled=settled,
        my_state=mine.state if mine else None,
        accepted=sum(1 for r in responses if r.state == ResponseState.ACCEPTED),
        responders=len(responses),
    )


def _coordinating(db: Session, room_id: int) -> Coordinating | None:
    """도는 조율. 한 방에 하나뿐이다(부분 유니크 인덱스)."""
    scheduling = db.exec(
        select(Scheduling).where(
            Scheduling.room_id == room_id,
            Scheduling.status == SchedulingStatus.RUNNING,
        )
    ).first()
    if scheduling is None or scheduling.id is None:
        return None
    return Coordinating(
        id=scheduling.id,
        topic=scheduling.topic,
        window_start=scheduling.window_start,
        window_end=scheduling.window_end,
        status=scheduling.status,
    )


def _my_tasks(db: Session, room_id: int, user_id: int, today: object) -> list[MyTask]:
    """내게 배정된 할 일. 기한 순 하나로만 준다(브리프).

    AI가 제안만 하고 아직 확정 안 된 것(confirmed=false)은 빼다. 홈은
    "지금 무엇을 봐야 하는지"를 보여 주는 자리고, 확정 전 제안은 회의록에서
    팀이 함께 고르는 것이라 내 할 일이 아니다.
    """
    rows = db.exec(
        select(Task).where(
            Task.room_id == room_id,
            Task.assignee_user_id == user_id,
            col(Task.confirmed).is_(True),
        )
    ).all()

    out: list[MyTask] = []
    for task in rows:
        if task.id is None:
            continue
        done = task.state == TaskState.DONE
        late = not done and task.due_date is not None and task.due_date < today
        out.append(
            MyTask(
                id=task.id,
                title=task.title,
                due_date=task.due_date,
                state=task.state,
                bucket=_bucket(task.due_date, done, today),
                late=late,
                blocked=task.state == TaskState.BLOCKED,
            )
        )

    # 기한 없는 것은 맨 뒤로. 완료는 그보다 더 뒤로 — 묶음 순서와 같다.
    묶음순서 = {"late": 0, "today": 1, "tomorrow": 2, "later": 3, "done": 4}
    out.sort(key=lambda t: (묶음순서[t.bucket], t.due_date is None, t.due_date or today))
    return out


def _bucket(due: object, done: bool, today: object) -> TaskBucket:
    """브리프의 다섯 갈래. 완료가 기한보다 먼저다 — 끝난 일은 안 늦는다."""
    if done:
        return "done"
    if due is None:
        return "later"
    assert hasattr(due, "toordinal") and hasattr(today, "toordinal")
    if due < today:  # type: ignore[operator]
        return "late"
    if due == today:
        return "today"
    if due == today + timedelta(days=1):  # type: ignore[operator]
        return "tomorrow"
    return "later"


def _unread(db: Session, room_id: int, user_id: int) -> int:
    """오른쪽 위 종에 붙는 숫자."""
    return db.exec(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.room_id == room_id,
            Notification.user_id == user_id,
            col(Notification.read_at).is_(None),
        )
    ).one()


def _joined(db: Session, room_id: int) -> int:
    """들어온 인원. 방을 막 만든 직후 화면이 초대 코드와 함께 보여 준다."""
    return db.exec(
        select(func.count())
        .select_from(Membership)
        .where(Membership.room_id == room_id)
    ).one()
