"""조율 라운드를 뒷단에서 돌린다.

**왜 뒷단인가.** 전에는 라운드가 `GET /stream` 응답 제너레이터 안에서 돌았다.
서버가 발언 하나를 만들어 그 HTTP 응답으로 흘려보낸 다음에야 다음 발언을
만들었다. 그러면 조율 전체가 **보는 사람 한 명의 연결 상태**에 묶인다:

  - 두 번째로 연 사람은 그때까지 쌓인 것만 보고 끝났다. 루프가 이미 돌고
    있어서 "재생" 갈래로 떨어졌기 때문이다.
  - 보던 사람이 탭을 닫으면 서버가 제너레이터를 더 안 돌려 조율이 거기서
    멈췄다. 상태가 running으로 남아 그 방은 새 조율을 못 열었다.

루프를 여기로 옮기면 둘 다 사라진다. 스트림은 DB를 읽어 흘려보내기만 하는
창이 되고, 누가 언제 열든 따라 읽고, 닫아도 아무 일이 없다.

**POST를 멈추지 않는다.** 조율 시작에서 라운드를 다 돌리면 POST가 10~20초
멈춰 그동안 화면이 빈다. 그래서 스레드를 띄우고 바로 돌아온다.

`run_rounds`는 한 줄도 안 고쳤다. 지금도 발언마다 commit하므로 읽는 쪽이
바로 본다. 여기서는 제너레이터를 비우기만 한다.
"""

from __future__ import annotations

import logging
import threading

from sqlmodel import Session

from app.meeting.agent_loop import run_rounds
from app.meeting.models import Scheduling
from app.shared import db as shared_db
from app.shared.enums import SchedulingStatus

log = logging.getLogger(__name__)


def start(scheduling_id: int) -> None:
    """라운드를 돌리기 시작하고 바로 돌아온다.

    데몬 스레드다. 서버를 끌 때 조율이 돌고 있어도 붙잡지 않는다 —
    시연 도중 Ctrl+C가 안 먹는 쪽이 더 나쁘다.

    테스트는 이 함수를 바꿔치기해 같은 자리에서 바로 돌린다(conftest).
    스레드는 자기 세션을 열어야 하는데 테스트는 세션 하나를 공유한다.
    """
    threading.Thread(
        target=run_to_end, args=(scheduling_id,), name=f"scheduling-{scheduling_id}", daemon=True
    ).start()


def run_to_end(scheduling_id: int) -> None:
    """끝까지 돌린다. 끝 상태는 run_rounds가 정한다.

    **터져도 running으로 남기지 않는다.** 남기면 부분 유니크 인덱스 때문에
    그 방이 새 조율을 영영 못 연다. 취소 엔드포인트가 없어서 DB를 비우는
    것 말고는 길이 없다. 그래서 무엇이 실패하든 failed로 떨군다.

    shortcut: 서버 프로세스가 루프 도중에 죽으면 그 조율은 running으로
    남는다. 여기서는 잡을 수 없다 — 되살리는 길이 필요해지면 팀장만 쓰는
    취소 엔드포인트를 더한다.
    """
    # 모듈로 부른다. 이름만 import하면 import 때 값이 굳어져 테스트가 세션을
    # 바꿔 끼울 수 없고, 테스트가 개발 DB에 쓰게 된다.
    with shared_db.background_session() as db:
        try:
            scheduling = db.get(Scheduling, scheduling_id)
            if scheduling is None:
                return
            for _ in run_rounds(db, scheduling):
                pass
        except Exception:
            log.exception("조율 %s이 돌다 터졌습니다", scheduling_id)
            _mark_failed(db, scheduling_id)


def _mark_failed(db: Session, scheduling_id: int) -> None:
    """상태만 failed로. 이것마저 실패하면 더 할 수 있는 게 없다."""
    try:
        db.rollback()  # 터진 트랜잭션으로는 아무것도 못 쓴다
        scheduling = db.get(Scheduling, scheduling_id)
        if scheduling is not None and scheduling.status == SchedulingStatus.RUNNING:
            scheduling.status = SchedulingStatus.FAILED
            db.add(scheduling)
            db.commit()
    except Exception:
        log.exception("조율 %s을 failed로 바꾸지도 못했습니다", scheduling_id)
