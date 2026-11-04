"""알림을 만드는 유일한 길.

`notification` 테이블은 Notice 도메인(레인 A) 것인데, 알림이 생기는 자리는
두 레인에 흩어져 있다 — 늦음·막힘·완료는 할 일(B)에서, 회의안·확정·30분 전은
조율(A)에서 나온다. 그래서 테이블 옆이 아니라 shared에 둔다. B가 A 도메인을
import하지 않아도 되고, `dedupe_key`를 만드는 규칙이 한 군데에만 있다.

규칙이 한 군데여야 하는 이유: 기한이 지난 할 일은 서버가 볼 때마다 늦음이다.
그때마다 행을 만들면 알림함이 같은 카드로 찬다. 두 사람이 각자 INSERT하면
한쪽은 키를 넣고 한쪽은 안 넣어서 중복이 샌다.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import Session

from app.notice.models import Notification
from app.shared import demo_clock
from app.shared.enums import NotificationKind


def emit(
    session: Session,
    *,
    room_id: int,
    user_ids: Sequence[int],
    kind: NotificationKind,
    reason: str,
    dedupe: str,
    task_id: int | None = None,
    meeting_id: int | None = None,
) -> int:
    """알림을 사람마다 한 장씩 만든다. 새로 만든 개수를 돌려준다.

    user_ids에 **본인을 넣을지는 부르는 쪽이 정한다.** 막혔다고 표시한
    사람에게 "현우가 막혔다고 표시했습니다"를 보내면 이상하지만, 완료는
    본인도 보고 싶을 수 있다. 그 판단은 도메인 몫이다.

    dedupe는 "무엇이 바뀌면 다시 떠야 하는가"다. 기한이 밀리면 다시 떠야
    하므로 기한을 녹여 넣는다(`"task42:due20261120"`). 앞에 kind를 붙이는
    것은 이 함수가 한다 — 같은 할 일의 늦음과 막힘이 서로를 막지 않게,
    부르는 쪽이 둘 다 `"task42"`로만 적는 실수를 공짜로 막는다.
    """
    if not user_ids:
        return 0

    # created_at을 직접 넣는다. Core insert는 SQLModel 필드의
    # default_factory를 돌리지 않아서 비워 두면 NOT NULL에 걸린다.
    #
    # real_now()가 아니라 시연 시계를 쓰는 이유: 알림함이 "5분 전"을 이 값으로
    # 보여 주고, 시연에서 날짜를 앞으로 옮겨 늦음 알림을 띄운다. 실제 시각으로
    # 찍으면 옮긴 시계와 어긋난 시간이 화면에 나온다.
    now = demo_clock.now(session)
    key = f"{kind.value}:{dedupe}"

    statement = (
        pg_insert(Notification)
        .values(
            [
                {
                    "room_id": room_id,
                    "user_id": user_id,
                    "kind": kind.value,
                    "reason": reason,
                    "dedupe_key": key,
                    "task_id": task_id,
                    "meeting_id": meeting_id,
                    "created_at": now,
                }
                for user_id in dict.fromkeys(user_ids)  # 중복 호출자 보호
            ]
        )
        # 먼저 SELECT해서 없으면 넣는 방식을 쓰지 않는다. 시연이 한 창에 폰
        # 화면 2개라 진짜로 동시에 눌리고, 그러면 둘이 같이 SELECT를 통과해
        # 한쪽이 UniqueViolation으로 500을 낸다. 이건 한 문장이라 틈이 없다.
        .on_conflict_do_nothing(index_elements=["user_id", "dedupe_key"])
        # RETURNING은 실제로 들어간 행만 준다. rowcount는 여러 행을 한 번에
        # 넣을 때 -1을 돌려줘서 "몇 장 새로 떴나"를 셀 수 없다.
        .returning(Notification.id)  # type: ignore[arg-type]
    )
    return len(session.execute(statement).all())
