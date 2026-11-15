"""레인 B 시드가 화면의 전제를 만족하는지 본다.

회의록·할 일 화면은 "담당자 없음 묶음", "늦음 뱃지", "AI 제안은 할 일
목록에 안 나옴"이 보여야 확인이 된다. 시드에서 이 값이 빠지면 API를 만들어
놓고도 화면에서 확인할 수 없다.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import Session, select

from app.meeting.models import Meeting
from app.minutes.models import Minutes, MinutesItem, Task, TranscriptSegment
from app.shared import demo_clock
from app.shared.enums import MinutesItemKind, MinutesStatus, TaskOrigin, TaskState
from tools.seed import seed

# 시연 시계의 오늘. 늦음은 이 날짜보다 기한이 앞선 것이다.
TODAY = date(2026, 11, 10)


def _tasks(session: Session, *, confirmed: bool) -> list[Task]:
    return list(session.exec(select(Task).where(Task.confirmed == confirmed)).all())


def test_지난_회의_한_건에_회의록과_요약이_붙는다(seeded: Session) -> None:
    minutes = seeded.exec(select(Minutes)).one()
    meeting = seeded.get(Meeting, minutes.meeting_id)

    assert meeting is not None and meeting.status == "done"
    assert minutes.status == MinutesStatus.DONE
    assert minutes.headline

    kinds = {
        item.kind for item in seeded.exec(select(MinutesItem)).all()
    }
    assert kinds == {
        MinutesItemKind.DECISION,
        MinutesItemKind.DISCUSSION,
        MinutesItemKind.PENDING,
    }


def test_원문은_줄_번호가_0부터_이어진다(seeded: Session) -> None:
    segments = seeded.exec(
        select(TranscriptSegment).order_by(TranscriptSegment.seq)
    ).all()

    assert [s.seq for s in segments] == list(range(len(segments)))
    assert len(segments) >= 3
    # 말한 사람을 모르는 줄도 정상이다
    assert any(s.speaker_user_id is None for s in segments)


def test_확정된_할_일은_상태_네_개가_다_보인다(seeded: Session) -> None:
    states = {t.state for t in _tasks(seeded, confirmed=True)}

    assert states == {
        TaskState.TODO,
        TaskState.DOING,
        TaskState.BLOCKED,
        TaskState.DONE,
    }


def test_담당자_없는_확정_할_일이_있다(seeded: Session) -> None:
    unassigned = [t for t in _tasks(seeded, confirmed=True) if t.assignee_user_id is None]

    assert unassigned


def test_기한이_지났는데_끝나지_않은_할_일이_있다(seeded: Session) -> None:
    late = [
        t
        for t in _tasks(seeded, confirmed=True)
        if t.due_date and t.due_date < TODAY and t.state != TaskState.DONE
    ]

    assert late


def test_확정_전_제안이_있고_확정_정보가_비어_있다(seeded: Session) -> None:
    proposals = _tasks(seeded, confirmed=False)

    assert len(proposals) >= 2
    assert all(p.confirmed_at is None and p.confirmed_by is None for p in proposals)
    assert all(p.origin == TaskOrigin.AI for p in proposals)
    # 담당자가 채워진 제안과 빈 제안이 둘 다 있다
    assert any(p.assignee_user_id for p in proposals)
    assert any(p.assignee_user_id is None for p in proposals)


def test_직접_추가한_할_일은_출처_회의가_없다(seeded: Session) -> None:
    manual = seeded.exec(select(Task).where(Task.origin == TaskOrigin.MANUAL)).all()

    assert manual
    assert all(t.meeting_id is None and t.confirmed for t in manual)


def _open_dues(session: Session) -> list[date]:
    """끝나지 않은 할 일과 제안의 기한."""
    return [
        t.due_date
        for t in session.exec(select(Task)).all()
        if t.due_date and t.state != TaskState.DONE
    ]


def test_본선_날에_넣어도_늦은_할_일은_하나뿐이다(session: Session) -> None:
    """시연 시계가 없어져 실제 날짜로 본다. 11/10에 박은 기한이면 전부 늦음이 된다."""
    final = date(2026, 11, 19)

    seed(session, today=final)

    dues = _open_dues(session)
    assert len([d for d in dues if d < final]) == 1
    assert min(d for d in dues if d >= final) == final + timedelta(days=2)


def test_기준일을_안_주면_시계의_오늘이_기준이다(session: Session) -> None:
    seed(session)

    today = demo_clock.now(session).date()
    late = [d for d in _open_dues(session) if d < today]
    assert late == [today - timedelta(days=2)]


def test_시각은_전부_오프셋이_붙어_있다(seeded: Session) -> None:
    for task in seeded.exec(select(Task)).all():
        assert task.created_at.tzinfo is not None
        if task.confirmed_at:
            assert task.confirmed_at.tzinfo is not None
