"""로그인과 "내가 누구인지".

Room 도메인이라 레인 표대로면 B(장연우) 것이다. 그런데 /me/* 전부가 사용자
없이는 아예 돌지 않아서 A가 먼저 깔았다. user 테이블은 건드리지 않았다 —
비밀번호 열을 더하는 것은 B의 일이고, 그 자리는 login() 안에 적어 뒀다.

지금은 인증이 아니라 사용자 선택이다. 이름을 보내면 그 사람이 된다.
시드 4명으로 시연하는 동안은 이게 충분하고, 비밀번호가 생기면 login()에
검사 한 줄이 들어갈 뿐 나머지는 그대로다.

쿠키는 main.py의 SessionMiddleware가 서명한다. 서명하지 않으면 쿠키 값이
그냥 "1"이라 누구나 다른 사람으로 바꿔 넣는다. db-설계.md가 "서명 쿠키를
쓰면 테이블이 필요 없습니다"로 정해 둔 길이다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import Session, SQLModel, select

from app.shared.db import session_dep
from app.shared.models import Membership, User

router = APIRouter(prefix="/sessions", tags=["auth"])

# 쿠키 안에 들어가는 키. 서명된 세션 딕셔너리의 한 칸이다.
SESSION_KEY = "user_id"


class LoginIn(SQLModel):
    name: str


class LoginOut(SQLModel):
    user_id: int
    name: str


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


@router.post("", status_code=status.HTTP_201_CREATED)
def login(
    body: LoginIn,
    request: Request,
    db: Session = Depends(session_dep),
) -> LoginOut:
    user = db.exec(select(User).where(User.name == body.name)).first()
    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "그 이름의 팀원이 없습니다."},
        )

    # 비밀번호가 생기면 바로 여기에 검사가 들어간다 (레인 B):
    #     if not verify(body.password, user.password_hash): raise 401
    # user 테이블에 열을 더하는 것까지가 B의 몫이라 지금은 비워 둔다.

    assert user.id is not None  # DB에서 읽어 온 행이라 항상 있다
    request.session[SESSION_KEY] = user.id
    return LoginOut(user_id=user.id, name=user.name)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
