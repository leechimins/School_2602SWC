"""FastAPI 앱.

시작할 때 테이블을 만들지 않는다. 그건 tools/reset_db.py만 한다. 서버가
뜰 때마다 스키마를 건드리면 배포에서 사고가 난다.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.demo.router import router as demo_router
from app.home.router import router as home_router
from app.integration.router import router as integration_router
from app.me.router import router as me_router
from app.me.schedule import items_router as schedule_items_router
from app.me.schedule import router as my_schedule_router
from app.meeting.router import router as meeting_router
from app.minutes.record_router import router as record_router
from app.minutes.suggest_router import router as suggest_router
from app.minutes.task_router import router as task_router
from app.notice.router import log_router as agent_log_router
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
# 배포(COOKIE_SECURE=true)에서는 쿠키를 https로만 보내고, SESSION_SECRET이 없으면
# 뜨지 않는다 — 기본값은 저장소에 공개돼 있어서 그걸로 서명하면 누구나 쿠키를 만든다.
# 로컬은 http라 기본값으로 그냥 뜬다.
COOKIE_SECURE = os.getenv("COOKIE_SECURE") == "true"
if COOKIE_SECURE and not os.getenv("SESSION_SECRET"):
    raise RuntimeError("COOKIE_SECURE=true인데 SESSION_SECRET이 없습니다. 배포 환경변수에 넣으세요.")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET") or "dev-only-비밀번호가-없는-동안만",
    same_site="lax",
    https_only=COOKIE_SECURE,
)

app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(home_router, prefix=API_PREFIX)
app.include_router(me_router, prefix=API_PREFIX)
app.include_router(my_schedule_router, prefix=API_PREFIX)
app.include_router(schedule_items_router, prefix=API_PREFIX)
app.include_router(meeting_router, prefix=API_PREFIX)
app.include_router(notice_router, prefix=API_PREFIX)
app.include_router(agent_log_router, prefix=API_PREFIX)
app.include_router(room_router, prefix=API_PREFIX)
app.include_router(record_router, prefix=API_PREFIX)
app.include_router(suggest_router, prefix=API_PREFIX)
app.include_router(task_router, prefix=API_PREFIX)
app.include_router(integration_router, prefix=API_PREFIX)
app.include_router(demo_router, prefix=API_PREFIX)


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


# 배포에서는 빌드된 프론트(npm run build의 dist)를 이 서버가 같이 준다. 주소가 하나라
# 쿠키와 SSE가 로컬과 똑같이 돈다. 로컬 개발은 Vite(5173)가 화면을 주므로 STATIC_DIR이 없다.
# 반드시 맨 끝에 둔다 — 아래 경로는 무엇이든 받으므로 앞에 있으면 API를 가린다.
STATIC_DIR = os.getenv("STATIC_DIR")
if STATIC_DIR:
    _static = Path(STATIC_DIR).resolve()
    _index = _static / "index.html"
    app.mount("/assets", StaticFiles(directory=_static / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        """public 폴더 파일(splash 그림 등)은 그대로, 나머지는 index.html.

        React Router 화면(/home 등)에서 새로고침하면 그 주소로 요청이 온다. 파일이 없으니
        index.html을 주고 화면 이동은 브라우저가 한다. /api 아래 없는 주소는 404 그대로.
        """
        if path.startswith("api/"):
            raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "없는 주소입니다."})
        file = (_static / path).resolve()
        if path and file.is_file() and file.is_relative_to(_static):
            return FileResponse(file)
        return FileResponse(_index)
