"""외부 연동 — 구글 캘린더 연결·끊기·동기화. 레인 B.

Swagger 그룹은 노션 API 명세에서 MyPage 아래지만, A의 `me` 그룹과 섞이지
않게 `integration`으로 둔다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session

from app.integration import service as integration
from app.integration.schemas import GoogleConnectIn, IntegrationOut
from app.minutes.models import CalendarLink
from app.shared.auth import current_user_id
from app.shared.db import session_dep
from app.shared.enums import CalendarKind

router = APIRouter(prefix="/me/integrations", tags=["integration"])


def _out(db: Session, user_id: int, link: CalendarLink | None) -> IntegrationOut:
    return IntegrationOut(
        kind=CalendarKind.GOOGLE,
        connected=link is not None,
        status=link.status if link else None,
        account=link.external_ref if link else None,
        last_synced_at=link.last_synced_at if link else None,
        imported_count=integration.imported_count(db, user_id),
    )


@router.post(
    "/google-calendar",
    response_model=IntegrationOut,
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
    - 연동은 선택입니다. 연결하지 않아도 시간표 직접 입력으로 계속 진행됩니다.
    """
    link = integration.connect(db, user_id, body.code)
    integration.sync(db, link)
    db.commit()
    return _out(db, user_id, link)


@router.post(
    "/google-calendar/sync",
    response_model=IntegrationOut,
    responses={404: {"description": "`NOT_CONNECTED` 연결 안 함"}},
    summary="구글 캘린더 동기화",
)
def sync_google(
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> IntegrationOut:
    """앞으로 5주(시연 시계 기준 오늘부터) 약속을 다시 읽어 바꿉니다.

    - 이전에 구글에서 들어온 약속을 지우고 새로 넣습니다. 직접 넣은 시간표는 그대로입니다.
    - 연결 안 했으면 404 `NOT_CONNECTED`.
    """
    link = integration.get_link(db, user_id, lock=True)
    if link is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_CONNECTED", "message": "구글 캘린더가 연결돼 있지 않아요."},
        )
    integration.sync(db, link)
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
