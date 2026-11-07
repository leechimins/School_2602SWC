"""시연 도구 — POST /demo/reset.

리허설 사이에 DB를 시드 상태로 되돌린다. 배포 서버에서 셸을 열 수 없어도
(tools/reset_db.py를 못 돌려도) 되게 HTTP로 둔다.

**열쇠가 있어야 돈다.** 시연 주소는 심사위원·관객 폰에도 열린다. 아무나 부르면
발표 도중에 데이터가 통째로 사라진다. 그래서 DEMO_RESET_KEY가 서버에 있고
요청 헤더 X-Demo-Key가 그와 같을 때만 지운다. 서버에 열쇠가 없으면 꺼져 있다.

테이블은 지우지 않고 행만 비운다(shared/db.truncate_all). 스키마가 바뀌었으면
이 길이 아니라 tools/reset_db.py다.
"""

from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlmodel import Session

from app.shared.db import session_dep, truncate_all
from tools.seed import seed

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/reset", status_code=status.HTTP_204_NO_CONTENT, summary="시드로 초기화")
def reset(
    x_demo_key: str | None = Header(default=None),
    db: Session = Depends(session_dep),
) -> None:
    """모든 행을 지우고 시드를 다시 넣습니다. 시연 시계도 실제 시각으로 돌아갑니다.

    - 헤더 `X-Demo-Key`가 서버의 `DEMO_RESET_KEY`와 같아야 합니다. 다르거나 서버에
      열쇠가 없으면 403 `FORBIDDEN`.
    - 다른 화면이 조율 스트림을 붙잡고 있어 5초 안에 못 지우면 409 `BUSY`. 아무것도
      안 지워집니다.
    - 사람 번호가 시드 순서대로 다시 매겨져서, 폰들의 로그인 쿠키는 같은 사람으로 그대로 씁니다.
    """
    key = os.getenv("DEMO_RESET_KEY")
    if not key or not x_demo_key or not secrets.compare_digest(x_demo_key, key):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "초기화 열쇠가 맞지 않습니다."},
        )

    # 지우기와 시드를 한 트랜잭션에 둔다. 시드가 실패하면 지운 것도 되돌아간다.
    try:
        db.execute(text("SET LOCAL lock_timeout = '5s'"))
        truncate_all(db)
        seed(db)  # 안에서 커밋한다
    except OperationalError:
        # shortcut: 열린 조율 스트림이 트랜잭션을 쥐고 있으면 기다리다 실패한다, 그 화면을 닫고 다시 누른다
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "BUSY", "message": "다른 화면이 아직 읽고 있어요. 잠시 뒤 다시 눌러 주세요."},
        )
