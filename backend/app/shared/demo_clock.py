"""시연 시계.

판정에 쓰는 "지금"은 전부 여기서 읽는다. datetime.now()도 SQL의 NOW()도
직접 쓰지 않는다 — 시연에서 날짜를 옮겨 늦음 판정과 30분 전 알림을 보여
줘야 하기 때문이다.

환경변수가 아니라 DB 한 행에 둔 이유: 명세에 PUT /demo/clock이 있어서
옮긴 값이 다음 요청에도 남아야 하고, 워커가 둘 이상이면 프로세스 메모리로는
안 된다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import Session

from app.shared.base import KST, real_now


def _state(session: Session):
    """demo_state 한 행을 가져온다. 없으면 만든다.

    import를 함수 안에서 하는 이유: shared가 demo를 모듈 수준에서
    끌어오면 방향이 거꾸로 걸린다.

    **ON CONFLICT로 넣는다.** 읽기 요청은 커밋을 안 하므로 여기서 만든
    행이 매번 버려지고, 그래서 시드를 안 돌린 DB에서는 행이 영영 안 생긴다.
    그 상태로 두 사람이 동시에 누르면 한쪽이 UniqueViolation으로 500이 되고
    그 요청이 통째로 사라진다. 한 문장이면 틈이 없다(shared/notify.emit과
    같은 길).

    created/updated를 직접 넣는 이유도 같다 — Core insert는 SQLModel 필드의
    default_factory를 안 돌려서 비워 두면 NOT NULL에 걸린다.
    """
    from app.demo.models import DemoState

    state = session.get(DemoState, 1)
    if state is None:
        session.execute(
            pg_insert(DemoState)
            .values(id=1, now_at=None, updated_at=real_now())
            .on_conflict_do_nothing(index_elements=["id"])
        )
        session.flush()
        state = session.get(DemoState, 1)
    if state is None:
        # DO NOTHING은 "다른 트랜잭션이 넣는 중"일 때도 아무것도 안 넣는다.
        # 그쪽이 되돌리면 행이 없는 채로 돌아온다. 드물지만 None을 내보내면
        # 부르는 쪽이 전부 터지므로 그냥 한 번 더 만든다.
        state = DemoState(id=1, now_at=None)
        session.add(state)
        session.flush()
    return state


def now(session: Session) -> datetime:
    """시연 시계가 가리키는 지금. 항상 aware(KST)."""
    state = _state(session)
    if state.now_at is None:
        return real_now()
    return state.now_at.astimezone(KST)


def set_clock(session: Session, when: datetime) -> datetime:
    """시계를 옮긴다. PUT /demo/clock."""
    if when.tzinfo is None:
        raise ValueError(
            "오프셋 없는 시각은 받지 않습니다. "
            "+09:00을 붙여 보내세요 — 명세의 권장 규칙 2입니다."
        )
    state = _state(session)
    state.now_at = when.astimezone(KST)
    state.updated_at = real_now()
    session.add(state)
    return state.now_at


def clear_clock(session: Session) -> None:
    """실제 시각으로 되돌린다. DELETE /demo/clock."""
    state = _state(session)
    state.now_at = None
    state.updated_at = real_now()
    session.add(state)
