"""Record 조회 조립 — 회의록 보기와 목록.

라우터에서 뺀 이유: 기록 시작·직접 쓰기·회의록 보기가 모두 같은
MeetingDetailOut을 돌려줘서 조립을 한 곳에 둔다.
"""

from __future__ import annotations

from sqlalchemy.orm import aliased
from sqlmodel import Session, col, func, select

from app.meeting.models import Meeting, MeetingResponse
from app.minutes.models import Minutes, MinutesItem, Task, TranscriptSegment
from app.minutes.schemas import (
    MeetingDetailOut,
    MeetingSummaryOut,
    MeetingTaskOut,
    MinutesOut,
    PersonOut,
    SuggestionOut,
    TranscriptLineOut,
)
from app.shared.enums import MeetingStatus, MinutesItemKind, ResponseState
from app.shared.models import Membership, User

# 회의록 목록에 나오는 회의. 회의안(proposed)과 취소된 회의는 기록할 대상이 아니다.
RECORDABLE = (MeetingStatus.CONFIRMED, MeetingStatus.DONE)


def member_names(db: Session, room_id: int) -> dict[str, int]:
    """이 방 팀원의 이름 → id. 직접 쓰기에서 화자를 가릴 때 쓴다."""
    rows = db.exec(
        select(User.name, User.id)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.room_id == room_id)
    ).all()
    return {name: user_id for name, user_id in rows}


def _attendees(db: Session, meeting_id: int) -> list[PersonOut]:
    rows = db.exec(
        select(User.id, User.name)
        .join(MeetingResponse, MeetingResponse.user_id == User.id)
        .where(
            MeetingResponse.meeting_id == meeting_id,
            MeetingResponse.state == ResponseState.ACCEPTED,
        )
        .order_by(User.id)
    ).all()
    return [PersonOut(user_id=user_id, name=name) for user_id, name in rows]


def _minutes(db: Session, meeting_id: int) -> MinutesOut | None:
    minutes = db.exec(select(Minutes).where(Minutes.meeting_id == meeting_id)).first()
    if minutes is None:
        return None
    items = db.exec(
        select(MinutesItem)
        .where(MinutesItem.minutes_id == minutes.id)
        .order_by(MinutesItem.seq)
    ).all()

    def texts(kind: MinutesItemKind) -> list[str]:
        return [item.text for item in items if item.kind == kind]

    return MinutesOut(
        headline=minutes.headline,
        status=minutes.status,
        decisions=texts(MinutesItemKind.DECISION),
        discussions=texts(MinutesItemKind.DISCUSSION),
        pendings=texts(MinutesItemKind.PENDING),
    )


def meeting_detail(db: Session, meeting: Meeting) -> MeetingDetailOut:
    assert meeting.id is not None

    lines = db.exec(
        select(TranscriptSegment, User.name)
        .join(User, User.id == TranscriptSegment.speaker_user_id, isouter=True)
        .where(TranscriptSegment.meeting_id == meeting.id)
        .order_by(TranscriptSegment.seq)
    ).all()

    assignee = aliased(User)
    confirmer = aliased(User)
    task_rows = db.exec(
        select(Task, assignee.name, confirmer.name)
        .join(assignee, assignee.id == Task.assignee_user_id, isouter=True)
        .join(confirmer, confirmer.id == Task.confirmed_by, isouter=True)
        .where(Task.meeting_id == meeting.id, col(Task.dropped).is_(False))
        .order_by(Task.id)
    ).all()

    return MeetingDetailOut(
        id=meeting.id,
        topic=meeting.topic,
        start_at=meeting.start_at,
        end_at=meeting.end_at,
        mode=meeting.mode,
        status=meeting.status,
        transcript_mode=meeting.transcript_mode,
        attendees=_attendees(db, meeting.id),
        transcript=[
            TranscriptLineOut(
                seq=segment.seq,
                speaker_user_id=segment.speaker_user_id,
                speaker_name=name,
                text=segment.text,
            )
            for segment, name in lines
        ],
        minutes=_minutes(db, meeting.id),
        tasks=[
            MeetingTaskOut(
                id=task.id,
                title=task.title,
                due_date=task.due_date,
                assignee_user_id=task.assignee_user_id,
                assignee_name=assignee_name,
                state=task.state,
                confirmed_by_name=confirmer_name,
                confirmed_at=task.confirmed_at,
            )
            for task, assignee_name, confirmer_name in task_rows
            if task.confirmed
        ],
        suggestions=[
            SuggestionOut(
                id=task.id,
                title=task.title,
                due_date=task.due_date,
                assignee_user_id=task.assignee_user_id,
                assignee_name=assignee_name,
            )
            for task, assignee_name, _ in task_rows
            if not task.confirmed
        ],
    )


def tasks_out(db: Session, task_ids: list[int]) -> list[MeetingTaskOut]:
    """확정된 할 일들을 담당자·확정한 사람 이름과 함께. 제안 확정 응답에 쓴다."""
    assignee = aliased(User)
    confirmer = aliased(User)
    rows = db.exec(
        select(Task, assignee.name, confirmer.name)
        .join(assignee, assignee.id == Task.assignee_user_id, isouter=True)
        .join(confirmer, confirmer.id == Task.confirmed_by, isouter=True)
        .where(col(Task.id).in_(task_ids))
        .order_by(Task.id)
    ).all()
    return [
        MeetingTaskOut(
            id=task.id,
            title=task.title,
            due_date=task.due_date,
            assignee_user_id=task.assignee_user_id,
            assignee_name=assignee_name,
            state=task.state,
            confirmed_by_name=confirmer_name,
            confirmed_at=task.confirmed_at,
        )
        for task, assignee_name, confirmer_name in rows
    ]


def meeting_list(db: Session, room_id: int) -> list[MeetingSummaryOut]:
    meetings = db.exec(
        select(Meeting)
        .where(Meeting.room_id == room_id, col(Meeting.status).in_(RECORDABLE))
        .order_by(col(Meeting.start_at).desc())
    ).all()
    ids = [m.id for m in meetings]
    if not ids:
        return []

    headlines = dict(
        db.exec(
            select(Minutes.meeting_id, Minutes.headline).where(
                col(Minutes.meeting_id).in_(ids)
            )
        ).all()
    )
    with_transcript = set(
        db.exec(
            select(TranscriptSegment.meeting_id)
            .where(col(TranscriptSegment.meeting_id).in_(ids))
            .distinct()
        ).all()
    )
    suggestion_counts = dict(
        db.exec(
            select(Task.meeting_id, func.count())
            .where(
                col(Task.meeting_id).in_(ids),
                col(Task.confirmed).is_(False),
                col(Task.dropped).is_(False),
            )
            .group_by(Task.meeting_id)
        ).all()
    )
    attendee_rows = db.exec(
        select(MeetingResponse.meeting_id, User.name)
        .join(User, User.id == MeetingResponse.user_id)
        .where(
            col(MeetingResponse.meeting_id).in_(ids),
            MeetingResponse.state == ResponseState.ACCEPTED,
        )
        .order_by(User.id)
    ).all()
    attendees: dict[int, list[str]] = {}
    for meeting_id, name in attendee_rows:
        attendees.setdefault(meeting_id, []).append(name)

    return [
        MeetingSummaryOut(
            id=m.id,
            topic=m.topic,
            headline=headlines.get(m.id),
            start_at=m.start_at,
            mode=m.mode,
            status=m.status,
            attendees=attendees.get(m.id, []),
            has_transcript=m.id in with_transcript,
            suggestion_count=suggestion_counts.get(m.id, 0),
        )
        for m in meetings
    ]
