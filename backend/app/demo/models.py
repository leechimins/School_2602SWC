"""Demo 도메인 — 시연 장치. 공통 레인.

시연 시계를 읽고 쓰는 길은 app/shared/demo_clock.py다. 여기는 그 값을
담아 두는 자리만 둔다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel

from app.shared.base import ts


class DemoState(SQLModel, table=True):
    """행이 하나만 있는 테이블.

    명세에 GET/PUT/DELETE /demo/clock이 있어서 시연 시계를 환경변수로 둘 수
    없다. PUT으로 옮긴 값이 다음 요청에도 남아야 하고, 워커가 둘 이상이면
    프로세스 메모리로도 안 된다. 한 행짜리 테이블이 제일 싼 공유 저장소다.
    """

    __tablename__ = "demo_state"
    __table_args__ = (CheckConstraint("id = 1", name="ck_demo_state_single_row"),)

    id: int | None = Field(default=1, primary_key=True)
    # 비어 있으면 실제 시각을 쓴다. DELETE /demo/clock이 이 상태로 돌린다.
    now_at: datetime | None = ts(nullable=True)
    updated_at: datetime = ts(auto_now=True)
