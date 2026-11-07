"""외부 연동 — 에브리타임 연결·끊기, 구글 캘린더 연결·끊기·동기화. 레인 B.

Swagger 그룹은 노션 API 명세에서 MyPage 아래지만, A의 `me` 그룹과 섞이지
않게 `integration`으로 둔다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session

from app.integration import everytime, everytime_service, timetable
from app.integration import google_calendar as google
from app.integration import service as integration
from app.integration.schemas import EverytimeConnectIn, GoogleConnectIn, IntegrationOut
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


# ── 에브리타임 ───────────────────────────────────────────────────────

_ET_INVALID = "링크를 읽지 못했어요. 직접 입력해 주세요."
_ET_RETRY = "에브리타임을 잠시 못 읽었어요. 잠시 후 다시 해 주세요."


@router.post(
    "/everytime",
    response_model=IntegrationOut,
    responses={
        400: {"description": "`EVERYTIME_LINK_INVALID` 링크 모양이 아니거나 시간표가 없음(비공개)"},
        503: {"description": "`EVERYTIME_UNAVAILABLE` 에브리타임 응답 없음·막힘. 다시 하기"},
    },
    summary="에브리타임 연결 · 다시 불러오기",
)
def connect_everytime(
    body: EverytimeConnectIn,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> IntegrationOut:
    """공유 링크(`everytime.kr/@아이디`)로 시간표를 읽어 수업을 넣습니다. 사람 확인 단계는 없습니다.

    - 과목 하나가 묶음 하나(`group_id`)이고, 요일마다 한 줄입니다. 학기 범위 밖의 주는 조율이 안 셉니다.
    - 이미 연결돼 있으면 "다시 불러오기"입니다. 이전 에브리타임 수업을 지우고 새로 넣습니다. 직접 넣은 일정은 그대로입니다.
    - 링크 모양이 아니거나 시간표가 비공개면 400 `EVERYTIME_LINK_INVALID`.
    - 에브리타임이 응답하지 않으면 503 `EVERYTIME_UNAVAILABLE`.
    - 실패하면 전에 들어온 수업은 남고, 연결돼 있었다면 상태가 `failed`가 됩니다.
    - 읽는 데 몇 초 걸립니다(브라우저로 공유 페이지를 엽니다).
    """
    if not everytime.configured():
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "EVERYTIME_UNAVAILABLE",
            "지금은 에브리타임을 연결할 수 없어요. 시간표를 직접 넣어 주세요.",
        )
    try:
        link, table = everytime_service.connect(db, user_id, body.url)
    except everytime.LinkInvalid:
        db.commit()  # 연결돼 있던 사람의 failed 표시
        raise _error(status.HTTP_400_BAD_REQUEST, "EVERYTIME_LINK_INVALID", _ET_INVALID) from None
    except everytime.EverytimeError:
        db.commit()
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE, "EVERYTIME_UNAVAILABLE", _ET_RETRY
        ) from None
    db.commit()
    return IntegrationOut(
        kind=CalendarKind.EVERYTIME,
        connected=True,
        status=link.status,
        account=f"everytime.kr/@{link.external_ref}",
        last_synced_at=link.last_synced_at,
        imported_count=timetable.class_count(db, user_id),
        term=timetable.term_label(table),
    )


@router.delete(
    "/everytime",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="에브리타임 끊기",
)
def disconnect_everytime(
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> Response:
    """연결을 끊고, 에브리타임에서 들어온 수업도 지웁니다.

    - 직접 넣은 일정·구글 약속은 그대로입니다.
    - 연결이 없어도 204입니다.
    """
    everytime_service.disconnect(db, user_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── 구글 캘린더 ──────────────────────────────────────────────────────


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
