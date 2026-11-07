"""수락·거절과 일정 보기. 실제 요청으로 본다.

여기서 지켜야 하는 것이 둘 있다.

**남의 점수가 안 샌다.** 회의 응답의 responders에는 score가 없고 burden
세 단계만 있다(명세 권장 규칙 3). JSON 키 자체를 확인한다 — 값만 보면
나중에 누가 필드를 더해도 테스트가 통과한다.

**마지막 수락이 확정한다.** 확정 버튼이 없으므로 그 요청 하나에서 상태·
확정 시각·양보 장부·합계·알림이 다 끝나야 한다. 셋 중 하나라도 빠지면
시연에서 회의가 영원히 "아직 한 명 남음"으로 남는다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.me.models import ScheduleItem
from app.meeting.agent_loop import run_rounds
from app.meeting.models import (
    CandidateSlot,
    Meeting,
    MeetingResponse,
    Scheduling,
    SlotCost,
    Utterance,
    YieldEntry,
)
from app.notice.models import Notification
from app.shared.base import KST
from app.shared.enums import (
    MeetingStatus,
    Mode,
    NotificationKind,
    ResponseState,
    SchedulingPhase,
    SchedulingStatus,
    SpeakerKind,
)
from app.shared.models import Membership, Room, User

API = "/api/v1"
MON = datetime(2026, 11, 9, 9, 0, tzinfo=KST)


@pytest.fixture(autouse=True)
def LLM을_끈다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "false")


class 팀:
    def __init__(self, room: Room, 지수: User, 현우: User, 민지: User) -> None:
        self.room = room
        self.지수 = 지수  # 팀장
        self.현우 = 현우
        self.민지 = 민지

    @property
    def room_id(self) -> int:
        assert self.room.id is not None
        return self.room.id


@pytest.fixture
def 방(session: Session) -> 팀:
    """세 명. 마지막 수락이 확정하는 것을 보려면 셋은 있어야 한다.

    둘이면 "한 명 수락 → 다음 수락이 확정"이라 중간 상태를 못 본다.
    """
    지수, 현우, 민지 = User(name="지수"), User(name="현우"), User(name="민지")
    session.add_all([지수, 현우, 민지])
    session.flush()
    room = Room(
        name="서비스디자인 팀 프로젝트",
        start_date=date(2026, 10, 20),
        due_date=date(2026, 12, 11),
        eval_method="최종 발표 + 시연",
        member_count=3,
        invite_code="T9K2QM",
        leader_user_id=지수.id,  # type: ignore[arg-type]
    )
    session.add(room)
    session.flush()
    session.add_all(
        [
            Membership(room_id=room.id, user_id=지수.id),  # type: ignore[arg-type]
            Membership(room_id=room.id, user_id=현우.id),  # type: ignore[arg-type]
            Membership(room_id=room.id, user_id=민지.id),  # type: ignore[arg-type]
        ]
    )
    session.commit()
    return 팀(room, 지수, 현우, 민지)


def _조율(session: Session, 방: 팀) -> Scheduling:
    s = Scheduling(
        room_id=방.room_id,
        started_by=방.지수.id,  # type: ignore[arg-type]
        topic="중간 발표 준비",
        window_start=MON,
        window_end=MON + timedelta(days=4),
        duration_min=120,
        mode=Mode.OFFLINE,
        status=SchedulingStatus.RUNNING,
    )
    session.add(s)
    session.flush()
    return s


def _후보(
    session: Session,
    scheduling: Scheduling,
    *,
    hour: int,
    점수: dict[int, int],
    못_오는_사람: int | None = None,
) -> CandidateSlot:
    slot = CandidateSlot(
        scheduling_id=scheduling.id,  # type: ignore[arg-type]
        start_at=MON.replace(hour=hour),
        end_at=MON.replace(hour=hour + 2),
        total_cost=float(sum(점수.values())),
        phase=SchedulingPhase.ABSENT if 못_오는_사람 else SchedulingPhase.ALL,
        round_no=1,
        absentee_user_id=못_오는_사람,
    )
    session.add(slot)
    session.flush()
    for user_id, score in 점수.items():
        session.add(
            SlotCost(
                candidate_slot_id=slot.id,  # type: ignore[arg-type]
                user_id=user_id,
                score=score,
                available=user_id != 못_오는_사람,
                reason="알바와 겹칩니다" if score >= 4 else "비어 있는 시간입니다",
            )
        )
    session.commit()
    return slot


def _합의된_회의(session: Session, 방: 팀) -> Meeting:
    """1라운드에 합의되는 조율을 돌려 proposed 회의를 만든다.

    점수를 전부 거절선(4) 아래로 둬서 전원이 수락한다. 지수 1(괜찮음),
    현우 2·민지 3(조금)이라 확정 때 현우·민지만 양보 점수를 받는다.
    """
    s = _조율(session, 방)
    _후보(
        session,
        s,
        hour=14,
        점수={방.지수.id: 1, 방.현우.id: 2, 방.민지.id: 3},  # type: ignore[dict-item]
    )
    list(run_rounds(session, s))
    meeting = session.exec(select(Meeting)).one()
    assert meeting.status == MeetingStatus.PROPOSED
    return meeting


def _조정된_회의(session: Session, 방: 팀) -> Meeting:
    """합의가 안 돼서 판단 에이전트가 정한 회의. 이미 확정된 상태다."""
    s = _조율(session, 방)
    _후보(
        session,
        s,
        hour=14,
        점수={방.지수.id: 1, 방.현우.id: 2, 방.민지.id: 5},  # type: ignore[dict-item]
    )
    list(run_rounds(session, s))
    session.refresh(s)
    assert s.status == SchedulingStatus.SETTLED
    return session.exec(select(Meeting)).one()


def _응답(client: TestClient, room_id: int, meeting_id: int, **body) -> object:
    return client.post(
        f"{API}/rooms/{room_id}/proposals/{meeting_id}/respond",
        json={"accept": True, **body},
    )


# ── 회의 보기 ─────────────────────────────────────────────────────


def test_내_점수는_숫자로_남의_점수는_단계로_나간다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """명세 권장 규칙 3. 숫자를 내보내면 제품의 핵심 약속이 깨진다."""
    meeting = _합의된_회의(session, 방)
    login("현우")

    body = client.get(f"{API}/rooms/{방.room_id}/proposals/{meeting.id}").json()

    assert body["my_score"] == 2  # 현우 것
    assert body["my_reason"]
    for responder in body["responders"]:
        # 키 자체가 없어야 한다. 값만 보면 나중에 누가 더해도 통과한다.
        assert "score" not in responder
        assert responder["burden"] in ("ok", "some", "much")

    단계 = {r["name"]: r["burden"] for r in body["responders"]}
    assert 단계 == {"지수": "ok", "현우": "some", "민지": "some"}


def test_회의가_왜_이_시간인지와_받을_양보_점수를_같이_준다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    meeting = _합의된_회의(session, 방)
    login("민지")

    body = client.get(f"{API}/rooms/{방.room_id}/proposals/{meeting.id}").json()

    assert body["rationale"]  # 판단 에이전트의 마지막 말
    assert body["scheduling_status"] == "agreed"
    assert body["my_yield_points"] == 1  # 불편 3 → +1
    assert body["can_respond"] is True
    assert body["feedback_only"] is False


def test_다른_방의_회의는_404다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """방을 안 보면 id만 바꿔 남의 방 회의를 열 수 있다.

    내가 **속한** 다른 방으로 물어본다. 안 속한 방은 require_member가 먼저
    403으로 끊어서 이 검사를 지나가지 않는다 — 그게 방이 있는지조차 안
    알려 주는 쪽이라 더 맞다.
    """
    meeting = _합의된_회의(session, 방)
    옆방 = Room(
        name="캡스톤 팀 프로젝트",
        start_date=date(2026, 10, 20),
        due_date=date(2026, 12, 11),
        eval_method="최종 발표",
        member_count=1,
        invite_code="X1Y2Z3",
        leader_user_id=방.지수.id,  # type: ignore[arg-type]
    )
    session.add(옆방)
    session.flush()
    session.add(Membership(room_id=옆방.id, user_id=방.지수.id))  # type: ignore[arg-type]
    session.commit()

    login("지수")
    assert (
        client.get(f"{API}/rooms/{옆방.id}/proposals/{meeting.id}").status_code == 404
    )


def test_로그인_없이는_회의를_못_본다(
    client: TestClient, session: Session, 방: 팀
) -> None:
    meeting = _합의된_회의(session, 방)
    res = client.get(f"{API}/rooms/{방.room_id}/proposals/{meeting.id}")
    assert res.status_code == 401


# ── 수락·거절 ───────────────────────────────────────────────────────


def test_마지막_수락이_회의를_확정한다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """확정 버튼이 없다. 이 요청 하나가 유일한 기회다."""
    meeting = _합의된_회의(session, 방)

    login("지수")
    첫번째 = _응답(client, 방.room_id, meeting.id).json()  # type: ignore[union-attr,attr-defined]
    assert 첫번째["confirmed_now"] is False
    assert 첫번째["pending_count"] == 2

    login("현우")
    _응답(client, 방.room_id, meeting.id)  # type: ignore[union-attr]

    login("민지")
    마지막 = _응답(client, 방.room_id, meeting.id).json()  # type: ignore[union-attr,attr-defined]
    assert 마지막["confirmed_now"] is True
    assert 마지막["meeting_status"] == "confirmed"
    assert 마지막["pending_count"] == 0

    session.expire_all()
    확정된것 = session.exec(select(Meeting)).one()
    assert 확정된것.status == MeetingStatus.CONFIRMED
    assert 확정된것.confirmed_at is not None


def test_확정될_때_양보_장부와_합계가_같이_올라간다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """합계를 안 올리면 다음 조율의 차등이 영원히 안 생긴다."""
    meeting = _합의된_회의(session, 방)
    for 이름 in ("지수", "현우", "민지"):
        login(이름)
        _응답(client, 방.room_id, meeting.id)  # type: ignore[union-attr]

    session.expire_all()
    장부 = {e.user_id: e.points for e in session.exec(select(YieldEntry)).all()}
    # 지수는 1점(괜찮음)이라 행이 없다. 현우 2·민지 3은 둘 다 +1.
    assert 장부 == {방.현우.id: 1, 방.민지.id: 1}

    합계 = {
        m.user_id: m.yield_total
        for m in session.exec(select(Membership)).all()
    }
    assert 합계 == {방.지수.id: 0, 방.현우.id: 1, 방.민지.id: 1}


def test_확정되면_확정_알림이_뜬다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    meeting = _합의된_회의(session, 방)
    for 이름 in ("지수", "현우", "민지"):
        login(이름)
        _응답(client, 방.room_id, meeting.id)  # type: ignore[union-attr]

    확정알림 = session.exec(
        select(Notification).where(
            Notification.kind == NotificationKind.MEETING_CONFIRMED
        )
    ).all()
    assert {n.user_id for n in 확정알림} == {방.지수.id, 방.현우.id, 방.민지.id}
    assert all(n.meeting_id == meeting.id for n in 확정알림)


def _두_후보로_합의된_회의(session: Session, 방: 팀) -> Meeting:
    """1라운드에 14시로 합의된 회의. 16시가 대안으로 남아 있다.

    점수를 모두 거절선(4) 아래로 둔다. 지수·현우는 14시를, 민지는 16시를
    원하지만 표가 14시에 더 모여 14시가 먼저 나간다. rounds_used는 1이라
    예산이 2라운드 남는다.
    """
    s = _조율(session, 방)
    _후보(session, s, hour=14, 점수={방.지수.id: 1, 방.현우.id: 2, 방.민지.id: 3})  # type: ignore[dict-item]
    _후보(session, s, hour=16, 점수={방.지수.id: 2, 방.현우.id: 2, 방.민지.id: 2})  # type: ignore[dict-item]
    list(run_rounds(session, s))
    meeting = session.exec(select(Meeting)).one()
    assert meeting.start_at.astimezone(KST).hour == 14
    assert meeting.status == MeetingStatus.PROPOSED
    return meeting


def _예산을_다_쓴_회의(session: Session, 방: 팀) -> Meeting:
    """3라운드를 다 쓰고 합의된 회의 — 다시 조율할 수 없다."""
    meeting = _합의된_회의(session, 방)
    s = session.get(Scheduling, meeting.scheduling_id)
    assert s is not None
    s.rounds_used = 3
    session.add(s)
    session.commit()
    return meeting


def test_거절하면_예산이_남을_때_바로_다시_조율한다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """브리프 11/5. 팀장 승인 없이, 거절한 사람이 누구든 자동으로 돈다."""
    old = _두_후보로_합의된_회의(session, 방)
    old_id = old.id
    login("현우")

    body = _응답(  # type: ignore[union-attr,attr-defined]
        client, 방.room_id, old_id, accept=False, feedback="그 시간엔 급한 일이 생겼어요"
    ).json()

    assert body["rerun"] is True
    assert body["rounds_left"] == 2  # 1라운드를 썼으니 2가 남았다
    assert body["meeting_status"] == "cancelled"

    session.expire_all()
    meetings = {m.status: m for m in session.exec(select(Meeting)).all()}
    assert set(meetings) == {MeetingStatus.CANCELLED, MeetingStatus.PROPOSED}
    # 거절된 14시는 다시 안 나오고 대안 16시가 나갔다.
    assert meetings[MeetingStatus.CANCELLED].start_at.astimezone(KST).hour == 14
    assert meetings[MeetingStatus.PROPOSED].start_at.astimezone(KST).hour == 16

    s = session.get(Scheduling, old.scheduling_id)
    assert s is not None
    assert s.status == SchedulingStatus.AGREED  # 다시 합의됐다
    assert s.rounds_used == 2  # 새로 3을 주지 않고 이어서 썼다

    # 새 회의는 처음부터 다시 답을 받는다.
    새 = meetings[MeetingStatus.PROPOSED]
    응답 = session.exec(
        select(MeetingResponse).where(MeetingResponse.meeting_id == 새.id)
    ).all()
    assert {r.state for r in 응답} == {ResponseState.PENDING}


def test_거절한_시간이_그_사람의_바쁨으로_들어간다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """이래야 다음 조율에서 같은 시간을 또 내놓지 않는다. 제목은 비운다."""
    old = _두_후보로_합의된_회의(session, 방)
    login("현우")
    _응답(client, 방.room_id, old.id, accept=False)  # type: ignore[union-attr]

    session.expire_all()
    item = session.exec(
        select(ScheduleItem).where(ScheduleItem.user_id == 방.현우.id)
    ).one()
    assert item.title is None  # 팀에는 "바쁨"으로만 나간다
    assert item.recurrence == "once"
    assert item.start_at == old.start_at
    assert item.end_at == old.end_at


def test_다시_조율해도_발언_번호가_이어진다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """uq_utterance_seq에 걸리면 이어 돌기가 터진다."""
    old = _두_후보로_합의된_회의(session, 방)
    앞 = len(session.exec(select(Utterance)).all())
    login("현우")
    _응답(client, 방.room_id, old.id, accept=False)  # type: ignore[union-attr]

    session.expire_all()
    seqs = [u.seq for u in session.exec(select(Utterance).order_by(col(Utterance.seq))).all()]
    assert seqs == list(range(1, len(seqs) + 1))
    assert len(seqs) > 앞
    # 판단 에이전트가 누가 왜 거절했는지 짚는다.
    판단 = session.exec(
        select(Utterance)
        .where(Utterance.speaker_kind == SpeakerKind.JUDGE)
        .order_by(col(Utterance.seq).desc())
    ).first()
    assert 판단 is not None and "현우" in 판단.text, 판단.text if 판단 else None


def test_다른_후보가_없으면_거절한_시간을_다시_확정하지_않는다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """후보가 하나뿐일 때. 조정이 "바로 확정"하는 길이라 막지 않으면, 현우가
    싫다고 한 그 시간이 그대로 확정되어 거절이 아무 뜻이 없어진다."""
    meeting = _합의된_회의(session, 방)  # 후보 하나, rounds_used=1
    login("현우")

    body = _응답(client, 방.room_id, meeting.id, accept=False).json()  # type: ignore[union-attr,attr-defined]

    assert body["rerun"] is True
    session.expire_all()
    m = session.exec(select(Meeting)).one()
    assert m.status == MeetingStatus.CANCELLED  # 확정되지 않았다
    s = session.get(Scheduling, meeting.scheduling_id)
    assert s is not None and s.status == SchedulingStatus.FAILED


def test_다시_조율하는_동안_옛_회의에_답하면_409다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    old = _두_후보로_합의된_회의(session, 방)
    login("현우")
    _응답(client, 방.room_id, old.id, accept=False)  # type: ignore[union-attr]

    login("민지")
    res = _응답(client, 방.room_id, old.id)  # type: ignore[union-attr]
    assert res.status_code == 409  # type: ignore[attr-defined]
    assert res.json()["code"] == "CLOSED"  # type: ignore[attr-defined]


def test_예산이_없으면_다시_조율하지_않고_회의가_그대로_남는다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    meeting = _예산을_다_쓴_회의(session, 방)
    login("현우")

    body = _응답(client, 방.room_id, meeting.id, accept=False).json()  # type: ignore[union-attr,attr-defined]

    assert body["rerun"] is False
    assert body["my_state"] == "declined"
    assert body["declined_count"] == 1
    assert body["meeting_status"] == "proposed"
    assert body["confirmed_now"] is False
    session.expire_all()
    assert session.exec(select(Meeting)).one().status == MeetingStatus.PROPOSED
    assert session.exec(select(YieldEntry)).all() == []
    assert session.exec(select(ScheduleItem)).all() == []  # 다시 돌지 않으니 바쁨도 없다


def test_예산이_없을_때_거절한_사람을_빼고_나머지가_수락하면_확정된다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """브리프 11/5: 그 사람은 불참으로 기록되고 회의는 선다."""
    meeting = _예산을_다_쓴_회의(session, 방)
    login("현우")
    _응답(client, 방.room_id, meeting.id, accept=False)  # type: ignore[union-attr]
    login("지수")
    중간 = _응답(client, 방.room_id, meeting.id).json()  # type: ignore[union-attr,attr-defined]
    assert 중간["confirmed_now"] is False  # 민지가 아직이다
    login("민지")
    마지막 = _응답(client, 방.room_id, meeting.id).json()  # type: ignore[union-attr,attr-defined]

    assert 마지막["confirmed_now"] is True
    session.expire_all()
    assert session.exec(select(Meeting)).one().status == MeetingStatus.CONFIRMED

    # 양보 점수는 와 주는 사람만. 현우(2점)는 거절했으니 못 받고 민지(3점)만 받는다.
    assert {y.user_id for y in session.exec(select(YieldEntry)).all()} == {방.민지.id}

    알림 = session.exec(
        select(Notification).where(Notification.kind == NotificationKind.MEETING_CONFIRMED)
    ).all()
    assert {n.user_id for n in 알림} == {방.지수.id, 방.현우.id, 방.민지.id}
    assert all("현우 님은 빠져요" in n.reason for n in 알림)


def test_피드백_한_줄이_남는다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    meeting = _합의된_회의(session, 방)
    login("민지")
    _응답(
        client,
        방.room_id,
        meeting.id,  # type: ignore[union-attr]
        feedback="다음부터는 오전 수업 끝나고가 좋아요",
    )

    mine = session.exec(
        select(MeetingResponse).where(MeetingResponse.user_id == 방.민지.id)
    ).one()
    assert mine.feedback == "다음부터는 오전 수업 끝나고가 좋아요"
    assert mine.responded_at is not None


def test_답할_사람이_아니면_403이다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """1명 불참안에서 빠지는 사람에게는 응답칸이 없다."""
    meeting = _합의된_회의(session, 방)
    session.exec(
        select(MeetingResponse).where(MeetingResponse.user_id == 방.민지.id)
    ).one()
    # 민지의 응답칸을 지워 "빠지는 사람" 상태를 만든다.
    for row in session.exec(
        select(MeetingResponse).where(MeetingResponse.user_id == 방.민지.id)
    ).all():
        session.delete(row)
    session.commit()

    login("민지")
    res = _응답(client, 방.room_id, meeting.id)  # type: ignore[union-attr]
    assert res.status_code == 403  # type: ignore[attr-defined]
    assert res.json()["code"] == "FORBIDDEN"  # type: ignore[attr-defined]


def test_로그인_없이는_못_답한다(
    client: TestClient, session: Session, 방: 팀
) -> None:
    meeting = _합의된_회의(session, 방)
    assert _응답(client, 방.room_id, meeting.id).status_code == 401  # type: ignore[union-attr,attr-defined]


# ── 조정된 회의는 피드백만 ──────────────────────────────────────────


def test_조정된_회의는_수락칸이_accepted로_깔린다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """시스템이 대신 수락한 것이다. 피드백을 받을 자리이기도 하다."""
    meeting = _조정된_회의(session, 방)
    login("지수")

    body = client.get(f"{API}/rooms/{방.room_id}/proposals/{meeting.id}").json()

    assert body["status"] == "confirmed"
    assert body["scheduling_status"] == "settled"
    assert body["my_state"] == "accepted"
    assert body["can_respond"] is False
    assert body["feedback_only"] is True


def test_조정된_회의에는_피드백만_저장된다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """브리프 11/5: 이미 확정이라 피드백만 받습니다.

    거절을 보내도 확정이 뒤집히지 않는다.
    """
    meeting = _조정된_회의(session, 방)
    login("민지")

    body = _응답(
        client,
        방.room_id,
        meeting.id,  # type: ignore[union-attr]
        accept=False,
        feedback="많이 불편했어요",
    ).json()  # type: ignore[union-attr,attr-defined]

    assert body["feedback_only"] is True
    assert body["my_state"] == "accepted"  # 거절로 바뀌지 않는다
    assert body["meeting_status"] == "confirmed"

    session.expire_all()
    assert session.exec(select(Meeting)).one().status == MeetingStatus.CONFIRMED
    mine = session.exec(
        select(MeetingResponse).where(MeetingResponse.user_id == 방.민지.id)
    ).one()
    assert mine.feedback == "많이 불편했어요"


def test_조정된_회의에_양보_점수가_두_번_들어가지_않는다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """조정할 때 이미 줬다. 피드백 길에서 또 주면 두 배가 된다."""
    meeting = _조정된_회의(session, 방)
    처음 = len(session.exec(select(YieldEntry)).all())
    assert 처음 > 0

    login("지수")
    _응답(client, 방.room_id, meeting.id, feedback="괜찮았어요")  # type: ignore[union-attr]

    session.expire_all()
    assert len(session.exec(select(YieldEntry)).all()) == 처음


# ── 일정 보기 ───────────────────────────────────────────────────────


def test_일정이_조율_중과_잡힌_것과_지난_것으로_갈린다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    meeting = _합의된_회의(session, 방)
    # 아직 안 끝난 조율 하나를 따로 둔다.
    _조율(session, 방)
    session.commit()
    login("지수")

    body = client.get(f"{API}/rooms/{방.room_id}/schedule").json()

    assert [c["topic"] for c in body["coordinating"]] == ["중간 발표 준비"]
    assert [m["id"] for m in body["upcoming"]] == [meeting.id]
    assert body["past"] == []
    # 회의도 자리를 잡아 둔다 — 아직 수락 전인데 목록에 보인다.
    assert body["upcoming"][0]["status"] == "proposed"
    assert body["upcoming"][0]["pending_count"] == 3
    assert body["upcoming"][0]["my_state"] == "pending"


def test_끝난_회의는_지난_것으로_간다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """가르는 기준은 시연 시계다. 프론트가 자기 시계로 가르면 어긋난다."""
    meeting = _합의된_회의(session, 방)
    meeting.start_at = MON - timedelta(days=7)
    meeting.end_at = MON - timedelta(days=7) + timedelta(hours=2)
    session.add(meeting)
    session.commit()
    login("지수")

    body = client.get(f"{API}/rooms/{방.room_id}/schedule").json()

    assert body["upcoming"] == []
    assert [m["id"] for m in body["past"]] == [meeting.id]


def test_조정으로_정해진_회의는_조정으로_표시된다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """화면이 "확정 · 조정"으로 그린다."""
    _조정된_회의(session, 방)
    login("지수")

    body = client.get(f"{API}/rooms/{방.room_id}/schedule").json()

    assert body["upcoming"][0]["settled"] is True
    assert body["coordinating"] == []  # 끝난 조율은 안 보인다


def test_합의로_정해진_회의는_조정_표시가_없다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    _합의된_회의(session, 방)
    login("지수")
    body = client.get(f"{API}/rooms/{방.room_id}/schedule").json()
    assert body["upcoming"][0]["settled"] is False


def test_남이_아닌_내_응답_상태가_나온다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """일정 목록은 보는 사람 기준이다."""
    meeting = _합의된_회의(session, 방)
    login("현우")
    _응답(client, 방.room_id, meeting.id)  # type: ignore[union-attr]

    login("현우")
    assert (
        client.get(f"{API}/rooms/{방.room_id}/schedule").json()["upcoming"][0][
            "my_state"
        ]
        == "accepted"
    )
    login("민지")
    assert (
        client.get(f"{API}/rooms/{방.room_id}/schedule").json()["upcoming"][0][
            "my_state"
        ]
        == "pending"
    )


def test_방_사람이_아니면_일정을_못_본다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    남 = User(name="연우")
    session.add(남)
    session.commit()
    login("연우")
    assert client.get(f"{API}/rooms/{방.room_id}/schedule").status_code == 403


def test_거절한_시간과_겹치는_후보도_다시_내놓지_않는다(
    client: TestClient, session: Session, 방: 팀, login
) -> None:
    """실서버로 돌려 보다 찾았다. 15:00–17:00을 거절했는데 다시 조율이 14:30–16:30을
    내놓았다 — 후보는 30분 간격이라 서로 겹치는데, 거절된 그 후보 하나만 뺐기 때문이다.

    14시가 1라운드에 합의된다. 15시는 14시와 겹치고, 18시는 안 겹친다.
    """
    s = _조율(session, 방)
    _후보(session, s, hour=14, 점수={방.지수.id: 1, 방.현우.id: 2, 방.민지.id: 3})  # type: ignore[dict-item]
    _후보(session, s, hour=15, 점수={방.지수.id: 2, 방.현우.id: 2, 방.민지.id: 2})  # type: ignore[dict-item]
    _후보(session, s, hour=18, 점수={방.지수.id: 2, 방.현우.id: 2, 방.민지.id: 2})  # type: ignore[dict-item]
    list(run_rounds(session, s))
    old = session.exec(select(Meeting)).one()
    assert old.start_at.astimezone(KST).hour == 14

    login("현우")
    _응답(client, 방.room_id, old.id, accept=False)  # type: ignore[union-attr]

    session.expire_all()
    새 = session.exec(select(Meeting).where(Meeting.status == MeetingStatus.PROPOSED)).one()
    assert 새.start_at.astimezone(KST).hour == 18  # 15시는 거절한 14–16시와 겹쳐서 빠진다
