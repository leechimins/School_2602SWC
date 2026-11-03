"""FastAPI 앱.

지금은 health뿐이다. D1에 hello world를 먼저 띄워 두면 마지막 날 배포에서
사고가 없다 — 13일 계획에 그렇게 적혀 있다.

시작할 때 테이블을 만들지 않는다. 그건 tools/reset_db.py만 한다. 서버가
뜰 때마다 스키마를 건드리면 배포에서 사고가 난다.
"""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy import text

from app.shared.db import engine

API_PREFIX = "/api/v1"

app = FastAPI(
    title="팀플 에이전트",
    openapi_url=f"{API_PREFIX}/openapi.json",
    docs_url=f"{API_PREFIX}/docs",
)


def _db_status() -> str:
    """DB가 붙는지 본다. 붙지 않아도 health 자체는 200을 준다.

    배포 플랫폼이 health로 살았는지 판단하므로, DB가 잠깐 끊겼다고 앱이
    죽은 것으로 취급되면 재시작 루프에 빠진다.
    """
    try:
        with engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - 무엇이든 사유만 알려 준다
        return f"fail: {type(exc).__name__}"
    return "ok"


@app.get(f"{API_PREFIX}/health")
def health() -> dict[str, str]:
    return {"status": "ok", "db": _db_status()}


@app.get("/health")
def health_bare() -> dict[str, str]:
    """배포 플랫폼이 보통 이 경로를 찌른다."""
    return health()
