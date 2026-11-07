"""에이전트가 한 일을 남기는 유일한 길. 브리프: "에이전트가 한 일 기록(무엇을, 왜)".

알림(shared/notify.py)과 다르다. 알림은 사람에게 "봐야 할 것"을 보내고 읽으면
사라진다. 이건 에이전트가 무엇을 왜 했는지 읽음 처리 없이 쌓아 둔다.

**방 전체가 보는 줄이다.** 그래서 사람별 불편 점수 같은 숫자를 넣지 않는다
(명세 권장 규칙 3). 부르는 쪽이 문장을 만들 때 지킨다.

한 곳에 두는 이유는 notify와 같다 — 레인 B(회의록 요약 같은 일)도 이걸
부르면 같은 화면에 쌓인다.
"""

from __future__ import annotations

from sqlmodel import Session

from app.notice.models import AgentLog
from app.shared import demo_clock


def record(db: Session, room_id: int, what: str, why: str) -> None:
    """한 줄을 남긴다. 커밋은 부르는 쪽이 한다 — 그 일과 같은 트랜잭션에 들어가야
    일은 됐는데 기록이 없거나, 기록만 남는 일이 없다.

    시각은 시연 시계다. 알림과 같은 시계를 봐야 "5분 전" 같은 표시가 맞는다.
    """
    db.add(
        AgentLog(
            room_id=room_id,
            what=what[:200],
            why=why[:300],
            created_at=demo_clock.now(db),
        )
    )
