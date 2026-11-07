"""외부 연동 — 구글 캘린더 연결·끊기·동기화. 레인 B.

Swagger 그룹은 노션 API 명세에서 MyPage 아래지만, A의 `me` 그룹과 섞이지
않게 `integration`으로 둔다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session

from app.integration import google_calendar as google
from app.integration import service as integration
from app.integration.schemas import GoogleConnectIn, IntegrationOut
from app.minutes.models import CalendarLink
from app.shared.auth import current_user_id
from app.shared.db import session_dep
from app.shared.enums import CalendarKind

router = APIRouter(prefix="/me/integrations", tags=["integration"])

_RETRY = "구글 캘린더를 잠시 못 읽었어요. 잠시 후 다시 해 주세요."

_ERRORS = {
    400: {"description": "`GOOGLE_CODE_INVALID` 코드가 잘못됐거나 이미 썼음"},
    404: {"description": "`NOT_CONNECTED` 연결 안 함"},
    409: {"description": "`GOOGLE_RECONNECT_NEEDED` 권한이 끊김. 다시 연결 필요"},
    503: {"description": "`GOOGLE_UNAVAILABLE` 구글 응답 없음 · 서버 설정 없음. 다시 하기"},
}


def _out(db: Session, user_id: int, link: CalendarLink | None) -> IntegrationOut:
    return IntegrationOut(
        kind=CalendarKind.GOOGLE,
        connected=link is not None,
        status=link.status if link else None,
        account=link.external_ref if link else None,
        last_synced_at=link.last_synced_at if link else None,
        imported_count=integration.imported_count(db, user_id),
    )


def _error(code: int, name: str, message: str) -> HTTPException:
    return HTTPException(code, detail={"code": name, "message": message})


def _unavailable(message: str = _RETRY) -> HTTPException:
    return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "GOOGLE_UNAVAILABLE", message)


def _reconnect() -> HTTPException:
    return _error(
        status.HTTP_409_CONFLICT,
        "GOOGLE_RECONNECT_NEEDED",
        "구글 캘린더 연결이 끊겼어요. 다시 연결해 주세요.",
    )


@router.post(
    "/google-calendar",
    response_model=IntegrationOut,
    responses={k: v for k, v in _ERRORS.items() if k in (400, 503)},
    summary="구글 캘린더 연결",
)
def connect_google(
    body: GoogleConnectIn,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> IntegrationOut:
    """팝업에서 받은 코드로 연결하고, 앞으로 5주 약속을 바로 읽어 옵니다.

    - 약속은 제목 없이 "바쁨"으로만 들어갑니다. 읽기 권한만 씁니다.
    - 이미 연결돼 있으면 새 계정·토큰으로 바꿉니다.
    - 코드가 잘못됐거나 이미 썼으면 400 `GOOGLE_CODE_INVALID`.
    - 연결은 됐는데 약속을 못 읽었으면 연결은 남기고 503 `GOOGLE_UNAVAILABLE` — 동기화로 다시 하세요.
    - 연동은 선택입니다. 실패해도 시간표 직접 입력으로 계속 진행됩니다.
    """
    if not google.configured():
        raise _unavailable("지금은 구글 캘린더를 연결할 수 없어요. 시간표를 직접 넣어 주세요.")
    try:
        link = integration.connect(db, user_id, body.code)
    except google.InvalidGrant:
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "GOOGLE_CODE_INVALID",
            "구글 연결이 끝나지 않았어요. 다시 연결해 주세요.",
        ) from None
    except google.GoogleError:
        raise _unavailable() from None

    try:
        integration.sync(db, link)
    except integration.ReconnectNeeded:
        db.commit()
        raise _reconnect() from None
    except google.GoogleError:
        db.commit()
        raise _unavailable(
            "연결은 됐는데 약속을 아직 못 읽었어요. 잠시 후 다시 해 주세요."
        ) from None
    db.commit()
    return _out(db, user_id, link)


@router.post(
    "/google-calendar/sync",
    response_model=IntegrationOut,
    responses={k: v for k, v in _ERRORS.items() if k in (404, 409, 503)},
    summary="구글 캘린더 동기화",
)
def sync_google(
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> IntegrationOut:
    """앞으로 5주(시연 시계 기준 오늘부터) 약속을 다시 읽어 바꿉니다.

    - 이전에 구글에서 들어온 약속을 지우고 새로 넣습니다. 직접 넣은 시간표는 그대로입니다.
    - 연결 안 했으면 404 `NOT_CONNECTED`.
    - 권한이 끊겼으면 상태가 `failed`가 되고 409 `GOOGLE_RECONNECT_NEEDED`. 전에 읽은 약속은 남습니다.
    - 구글이 응답하지 않으면 503 `GOOGLE_UNAVAILABLE`. 전에 읽은 약속은 남습니다.
    """
    link = integration.get_link(db, user_id, lock=True)
    if link is None:
        raise _error(
            status.HTTP_404_NOT_FOUND, "NOT_CONNECTED", "구글 캘린더가 연결돼 있지 않아요."
        )
    if not google.configured():
        raise _unavailable()
    try:
        integration.sync(db, link)
    except integration.ReconnectNeeded:
        db.commit()
        raise _reconnect() from None
    except google.GoogleError:
        db.rollback()
        raise _unavailable() from None
    db.commit()
    return _out(db, user_id, link)


@router.delete(
    "/google-calendar",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="구글 캘린더 끊기",
)
def disconnect_google(
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> Response:
    """연결을 끊고, 구글에서 들어온 "바쁨" 약속도 지웁니다.

    - 직접 넣은 시간표는 그대로입니다.
    - 연결이 없어도 204입니다.
    - 구글 쪽 권한은 사용자가 구글 계정 설정에서 직접 지웁니다.
    """
    integration.disconnect(db, user_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
