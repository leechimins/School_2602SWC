"""로그인과 "내가 누구인지".

로그인은 구글 하나다(POST /sessions/google). 11/15에 이름 로그인(POST /sessions에
이름만 보내면 그 사람이 되던 길)을 지웠다 — 배포 주소에서는 누구든 시드 이름을 쳐서
그 사람이 될 수 있어서다. 테스트는 conftest.py가 테스트에서만 같은 주소를 붙여 쓴다.

쿠키는 main.py의 SessionMiddleware가 서명한다. 서명하지 않으면 쿠키 값이
그냥 "1"이라 누구나 다른 사람으로 바꿔 넣는다. db-설계.md가 "서명 쿠키를
쓰면 테이블이 필요 없습니다"로 정해 둔 길이다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, select

from app.integration import google_calendar as google
from app.shared.db import session_dep
from app.shared.models import Membership, User

router = APIRouter(prefix="/sessions", tags=["auth"])

# 쿠키 안에 들어가는 키. 서명된 세션 딕셔너리의 한 칸이다.
SESSION_KEY = "user_id"


class LoginOut(SQLModel):
    user_id: int
    name: str


class GoogleLoginIn(SQLModel):
    credential: str  # 구글 로그인 버튼이 준 ID 토큰


class GoogleLoginOut(LoginOut):
    is_new: bool  # 처음 왔다 — 화면이 초대 코드 입력·방 만들기로 간다


def current_user_id(request: Request) -> int:
    """지금 요청을 보낸 사람. 로그인 안 했으면 401.

    한 브라우저 창에 두 사람을 동시에 띄우는 건 이 길로는 안 된다 — 쿠키
    저장소가 브라우저 프로필당 하나라서다(db-설계.md §9-1). 시연에서 폰 화면
    2개로 가기로 정하면 여기에 헤더를 먼저 보는 갈래를 더한다.
    """
    user_id = request.session.get(SESSION_KEY)
    if user_id is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHENTICATED", "message": "로그인이 필요합니다."},
        )
    return int(user_id)


def require_member(db: Session, room_id: int, user_id: int) -> None:
    """이 방의 팀원인지. 아니면 403.

    방이 없을 때도 403이다 — 없는 방 번호를 넣어 보는 쪽에게 "그 방은
    없습니다"와 "당신은 팀원이 아닙니다"를 구분해 줄 이유가 없다.
    """
    found = db.exec(
        select(Membership.id).where(
            Membership.room_id == room_id, Membership.user_id == user_id
        )
    ).first()
    if found is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "이 방의 팀원이 아닙니다."},
        )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/google", status_code=status.HTTP_201_CREATED)
def login_google(
    body: GoogleLoginIn,
    request: Request,
    db: Session = Depends(session_dep),
) -> GoogleLoginOut:
    """구글 로그인. 같은 구글 계정이면 같은 사람이고, 처음이면 만든다.

    - 토큰이 틀렸거나 만료됐거나 다른 앱 것이면 401 `UNAUTHENTICATED`.
    - 구글이 안 받으면 503 `GOOGLE_UNAVAILABLE`, 서버에 클라이언트 ID가 없으면 503
      `GOOGLE_NOT_CONFIGURED`.
    """
    if google.login_client_id() is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "GOOGLE_NOT_CONFIGURED", "message": "구글 로그인이 아직 설정되지 않았어요."},
        )
    try:
        sub, name = google.verify_id_token(body.credential)
    except google.InvalidGrant:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHENTICATED", "message": "구글 로그인을 다시 해 주세요."},
        ) from None
    except google.GoogleError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "GOOGLE_UNAVAILABLE", "message": "구글에 연결할 수 없어요. 잠시 뒤 다시 해 주세요."},
        ) from None

    user = db.exec(select(User).where(User.google_sub == sub)).first()
    is_new = user is None
    if user is None:
        user = User(name=name.strip()[:20] or "팀원", google_sub=sub)
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            # 같은 계정으로 두 창에서 동시에 처음 들어왔다. 먼저 만든 쪽을 쓴다.
            db.rollback()
            user = db.exec(select(User).where(User.google_sub == sub)).one()
            is_new = False

    assert user.id is not None
    request.session[SESSION_KEY] = user.id
    return GoogleLoginOut(user_id=user.id, name=user.name, is_new=is_new)
