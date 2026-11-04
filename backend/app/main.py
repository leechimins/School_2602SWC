"""FastAPI 앱.

시작할 때 테이블을 만들지 않는다. 그건 tools/reset_db.py만 한다. 서버가
뜰 때마다 스키마를 건드리면 배포에서 사고가 난다.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.me.router import router as me_router
from app.meeting.router import router as meeting_router
from app.minutes.router import router as minutes_router
from app.notice.router import router as notice_router
from app.room.router import router as room_router
from app.shared.auth import router as auth_router
from app.shared.db import engine, register_models

API_PREFIX = "/api/v1"

# 테이블을 "만들지"는 않는다. 모델 클래스를 metadata에 등록만 한다.
#
# 이게 없으면 도메인을 넘는 FK가 풀리지 않는다. notification.task_id는
# app/minutes/models.py(레인 B)의 task를 가리키는데, 라우터들은 각자 자기
# 도메인 모델만 import하므로 app.minutes.models를 아무도 끌어오지 않는다.
# 그러면 알림에 쓰기를 하는 순간 NoReferencedTableError로 터진다.
#
# DB를 건드리지 않으므로(import뿐) 배포에서 사고가 날 일은 없다. 테이블을
# 만드는 것은 그대로 tools/reset_db.py만 한다.
register_models()

app = FastAPI(
    title="팀플 에이전트",
    openapi_url=f"{API_PREFIX}/openapi.json",
    docs_url=f"{API_PREFIX}/docs",
)

# 세션 쿠키를 서명한다. 서명하지 않으면 쿠키 값이 그냥 "1"이라 누구나 다른
# 사람으로 바꿔 넣는다.
#
# 기본값을 둔 이유: 지금 로그인은 비밀번호가 없어서(shared/auth.py) 쿠키를
# 위조하는 것과 그 이름으로 로그인하는 것이 같다 — 비밀이 아직 아무것도
# 지키지 않는다. 그래서 .env에 한 줄이 없다고 서버가 안 뜨게 하지 않았다.
# 레인 B가 비밀번호를 붙이는 순간부터는 이 값이 진짜 비밀이 되므로 .env에
# 반드시 넣어야 한다.
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET") or "dev-only-비밀번호가-없는-동안만",
    same_site="lax",
)

app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(me_router, prefix=API_PREFIX)
app.include_router(meeting_router, prefix=API_PREFIX)
app.include_router(notice_router, prefix=API_PREFIX)
app.include_router(room_router, prefix=API_PREFIX)
app.include_router(minutes_router, prefix=API_PREFIX)


# 에러 모양을 명세에 맞춘다 — {"code": ..., "message": 화면에 그대로 띄울 한 줄}.
# FastAPI 기본값은 {"detail": ...}로 한 겹 싸고 검사 실패는 422를 준다. 그대로
# 두면 프론트가 엔드포인트 수만큼 문구 매핑 테이블을 만들게 된다(명세 권장 규칙 1).
@app.exception_handler(HTTPException)
def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        return JSONResponse(exc.detail, status_code=exc.status_code)
    return JSONResponse(
        {"code": "ERROR", "message": str(exc.detail)}, status_code=exc.status_code
    )


@app.exception_handler(RequestValidationError)
def invalid_input(request: Request, exc: RequestValidationError) -> JSONResponse:
    """422를 명세의 400 INVALID_INPUT으로 바꾼다.

    field는 첫 번째 잘못된 칸의 이름이다. 명세가 "field로 어느 칸인지"를
    요구하고, 한 번에 하나만 고치게 하는 쪽이 화면에서 쓰기 쉽다.
    """
    first = exc.errors()[0]
    # loc은 ("body", "day_start", "hour12")처럼 온다. 맨 끝이 칸 이름이다.
    field = str(first["loc"][-1]) if first.get("loc") else None
    return JSONResponse(
        {
            "code": "INVALID_INPUT",
            "field": field,
            "message": f"입력을 확인해 주세요: {first.get('msg', '잘못된 값')}",
        },
        status_code=400,
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
