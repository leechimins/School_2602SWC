"""외부 연동 — 에브리타임 연결(링크·캡처)·끊기, 구글 캘린더 연결·끊기·동기화. 레인 B.

Swagger 그룹은 노션 API 명세에서 MyPage 아래지만, A의 `me` 그룹과 섞이지
않게 `integration`으로 둔다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import Session

from app.integration import capture, everytime, everytime_service, timetable
from app.integration import google_calendar as google
from app.integration import service as integration
from app.integration.schemas import (
    CaptureClass,
    CapturePreviewOut,
    CaptureSaveIn,
    EverytimeConnectIn,
    GoogleConnectIn,
    IntegrationOut,
)
from app.minutes.models import CalendarLink
from app.shared import demo_clock
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

_ET_INVALID = "에타 시간표에서 복사한 공유 링크를 붙여 넣어 주세요."
_ET_NOT_FOUND = "시간표를 찾지 못했어요. 에브리타임에서 시간표가 전체 공개인지 확인해 주세요."
_ET_RETRY = "에브리타임을 잠시 못 읽었어요. 잠시 후 다시 해 주세요."


@router.post(
    "/everytime",
    response_model=IntegrationOut,
    responses={
        400: {"description": "`EVERYTIME_LINK_INVALID` 링크 모양이 아니거나 시간표가 없음(비공개)"},
        503: {
            "description": "`EVERYTIME_UNAVAILABLE` 에브리타임 응답 없음·막힘. 다시 하기 / "
            "`EVERYTIME_NOT_CONFIGURED` 서버에 연동이 깔려 있지 않음. 다시 해도 안 되니 직접 입력으로"
        },
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
    - 링크 모양이 아니거나 시간표가 비공개면 400 `EVERYTIME_LINK_INVALID`. 문구가 다르다(모양 틀림 → 링크 모양 안내, 시간표 없음 → 전체 공개 확인 안내).
    - 에브리타임이 응답하지 않거나 막으면 503 `EVERYTIME_UNAVAILABLE`. 다시 하면 될 수 있습니다.
    - 서버에 연동이 깔려 있지 않으면 503 `EVERYTIME_NOT_CONFIGURED`. 다시 해도 안 되니 직접 입력으로 안내합니다.
    - 실패하면 전에 들어온 수업은 남고, 연결돼 있었다면 상태가 `failed`가 됩니다.
    - 지난 학기 시간표도 거절하지 않고 넣습니다(조율은 학기 범위 밖을 안 셉니다). 대신 `term_state`가 `past`이니 이번 학기 링크를 넣으라고 안내합니다.
    - 읽는 데 2~4초 걸립니다.
    """
    if not everytime.configured():
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "EVERYTIME_NOT_CONFIGURED",
            "지금은 에브리타임을 연결할 수 없어요. 시간표를 직접 넣어 주세요.",
        )
    try:
        link, table = everytime_service.connect(db, user_id, body.url)
    except everytime.LinkInvalid as exc:
        db.commit()  # 연결돼 있던 사람의 failed 표시
        # 코드는 같고 문구만 다르다. 비공개가 가장 흔해서 공개 설정을 알려 준다.
        message = _ET_NOT_FOUND if isinstance(exc, everytime.TimetableNotFound) else _ET_INVALID
        raise _error(status.HTTP_400_BAD_REQUEST, "EVERYTIME_LINK_INVALID", message) from None
    except everytime.EverytimeError:
        db.commit()
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE, "EVERYTIME_UNAVAILABLE", _ET_RETRY
        ) from None
    db.commit()
    return _everytime_out(db, user_id, link, table)


def _everytime_out(
    db: Session, user_id: int, link: CalendarLink, table: timetable.Timetable
) -> IntegrationOut:
    from_capture = link.external_ref == everytime_service.CAPTURE_REF
    return IntegrationOut(
        kind=CalendarKind.EVERYTIME,
        connected=True,
        status=link.status,
        account="시간표 캡처" if from_capture else f"everytime.kr/@{link.external_ref}",
        last_synced_at=link.last_synced_at,
        imported_count=timetable.class_count(db, user_id),
        term=timetable.term_label(table),
        term_state=timetable.term_state(table, demo_clock.now(db).date()),
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


# ── 에브리타임 시간표 캡처 (#66) ─────────────────────────────────────

_IMAGE_INVALID = "PNG·JPG·WEBP 캡처만 올릴 수 있어요."
_IMAGE_TOO_LARGE = "5MB 이하 캡처로 올려 주세요."


async def _image_body(request: Request) -> tuple[bytes, str]:
    """요청 본문 = 이미지 파일 그대로. 형식은 Content-Type으로 본다.

    녹음 업로드와 같은 방식: 선언된 길이로 먼저 거르고, 읽는 중에도 한도를 넘으면 끊는다.
    """
    mime = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
    if mime not in capture.MIME_TYPES:
        raise _error(status.HTTP_400_BAD_REQUEST, "IMAGE_INVALID", _IMAGE_INVALID)
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > capture.MAX_BYTES:
        raise _error(status.HTTP_400_BAD_REQUEST, "IMAGE_TOO_LARGE", _IMAGE_TOO_LARGE)
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > capture.MAX_BYTES:
            raise _error(status.HTTP_400_BAD_REQUEST, "IMAGE_TOO_LARGE", _IMAGE_TOO_LARGE)
    if not body:
        raise _error(status.HTTP_400_BAD_REQUEST, "IMAGE_INVALID", _IMAGE_INVALID)
    return bytes(body), mime


@router.post(
    "/everytime/capture/preview",
    response_model=CapturePreviewOut,
    responses={
        400: {
            "description": "`IMAGE_INVALID` PNG·JPG·WEBP 아님 / `IMAGE_TOO_LARGE` 5MB 초과 / "
            "`NOT_EVERYTIME` 에브리타임 시간표 화면이 아님 / `CAPTURE_PAST_TERM` 지난 학기 시간표"
        },
        503: {"description": "`CAPTURE_READ_FAILED` AI 실패·시간 초과. 같은 캡처로 다시 하기"},
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {t: {"schema": {"type": "string", "format": "binary"}} for t in capture.MIME_TYPES},
        }
    },
    summary="에브리타임 시간표 캡처 읽기 (저장 안 함)",
)
def preview_capture(
    user_id: int = Depends(current_user_id),  # 로그인부터 본다(본문을 읽기 전에 401)
    image: tuple[bytes, str] = Depends(_image_body),
    db: Session = Depends(session_dep),
) -> CapturePreviewOut:
    """에브리타임 시간표 화면 캡처를 읽어 수업 목록만 돌려줍니다. **저장하지 않습니다.**

    - 요청 본문은 이미지 파일 그대로입니다(`Content-Type: image/png|jpeg|webp`, 5MB까지).
    - 칸의 위치(요일·시작·끝)는 캡처의 격자를 픽셀로 재서 5분 단위까지 맞추고, 과목명과 학기는 AI가 읽습니다.
    - 에브리타임 시간표가 아니면 400 `NOT_EVERYTIME`. 직접 입력·구글 캘린더가 따로 있어서 다른 표는 받지 않습니다.
    - 지난 학기 시간표면 400 `CAPTURE_PAST_TERM`. 확정 요청에는 학기가 오지 않아(두 요청 사이를
      서버가 기억하지 않음) 확정은 오늘 학기로 저장합니다. 지난 학기 수업이 이번 학기 회의 시간을
      막지 않게 여기서 거릅니다. 학기를 못 읽었거나 다음 학기면 받습니다.
    - 수업을 하나도 못 읽으면 빈 목록입니다.
    - 사람이 확인·수정한 목록을 `POST /me/integrations/everytime/capture`로 보내야 일정에 들어갑니다.
      `year`·`semester`는 그대로 돌려보냅니다.
    - 읽는 데 10초 안팎 걸립니다.
    """
    data, mime = image
    try:
        result = capture.read(data, mime)
    except capture.NotEverytime:
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "NOT_EVERYTIME",
            "에브리타임 시간표 화면 캡처만 읽을 수 있어요.",
        ) from None
    except capture.CaptureError:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "CAPTURE_READ_FAILED",
            "시간표를 잠시 못 읽었어요. 잠시 후 다시 해 주세요.",
        ) from None
    table = result.timetable()
    if timetable.term_state(table, demo_clock.now(db).date()) == timetable.TermState.PAST:
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "CAPTURE_PAST_TERM",
            f"{timetable.term_label(table)} 시간표예요. 이번 학기 시간표를 캡처해 주세요.",
        )
    return CapturePreviewOut(
        classes=[
            CaptureClass(title=c.title, weekday=c.weekday, start_min=c.start_min, end_min=c.end_min)
            for c in result.classes
        ],
        year=result.year,
        semester=result.semester,
        term=timetable.term_label(table),
    )


@router.post(
    "/everytime/capture",
    response_model=IntegrationOut,
    responses={400: {"description": "`INVALID_INPUT` 과목명 빈칸·끝 ≤ 시작 등"}},
    summary="에브리타임 시간표 캡처 확정 (저장)",
)
def save_capture(
    body: CaptureSaveIn,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> IntegrationOut:
    """사람이 확인·수정한 수업 목록을 넣습니다. 응답은 링크 연결과 같습니다.

    - 이전 에브리타임 수업(링크로 넣었든 캡처로 넣었든)을 지우고 이것으로 바꿉니다. 직접 넣은 일정은 그대로입니다.
    - `year`·`semester`는 미리보기에서 받은 값을 그대로 보냅니다. 없으면 오늘(시연 시계)이 속한 학기로 봅니다.
    - 지난 학기 캡처여도 넣고 `term_state`가 `past`입니다(조율은 학기 범위 밖을 안 셉니다).
    - 과목명이 같으면 한 묶음(`group_id`)이 됩니다.
    """
    classes = [
        capture.CapturedClass(c.title, c.weekday, c.start_min, c.end_min) for c in body.classes
    ]
    link, table = everytime_service.save_capture(
        db,
        user_id,
        classes,
        year=body.year,
        semester=body.semester,
        today=demo_clock.now(db).date(),
    )
    db.commit()
    return _everytime_out(db, user_id, link, table)


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
    """팝업에서 받은 코드로 연결하고, 오늘부터 팀플 마감일까지(방이 없으면 5주) 약속을 바로 읽어 옵니다.

    - 약속 제목은 본인 일정 화면에만 보이고, 팀원과 조율에는 "바쁨"으로만 갑니다. 읽기 권한만 씁니다.
    - 팀장이 조율을 시작하면 그 기간 약속을 구글에서 다시 읽습니다.
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
    """오늘(시연 시계 기준)부터 팀플 마감일까지(방이 없으면 5주) 약속을 다시 읽어 바꿉니다.

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
