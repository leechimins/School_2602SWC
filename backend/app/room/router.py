"""Room — 내 계정, 방, 초대 코드.

경로가 `/me`와 `/rooms/*`로 갈려 prefix를 두지 않는다.

방을 만든 사람이 그 방의 팀장이다. 브리프의 "방 생성하기는 팀장만"은
만든 사람이 팀장이 된다는 뜻으로 읽었다 — 방이 생기기 전에는 팀장을 가릴
자리가 없다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.errors import UniqueViolation
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.room.schemas import (
    InvitePreviewOut,
    JoinIn,
    MeOut,
    MyRoomOut,
    RoomCreateIn,
    RoomOut,
)
from app.room.service import joined_count, new_invite_code, room_out
from app.shared.auth import current_user_id, require_member
from app.shared.db import session_dep
from app.shared.models import Membership, Room, User

router = APIRouter(tags=["room"])

# 초대 코드가 겹쳐 다시 뽑는 횟수. 31자 6자리라 겹칠 일이 거의 없다.
INVITE_RETRIES = 5


def _constraint(exc: IntegrityError) -> str | None:
    orig = exc.orig
    if isinstance(orig, UniqueViolation):
        return orig.diag.constraint_name
    return None


def _room_by_code(db: Session, code: str) -> Room:
    # 소문자로 쳐도 들어가게 한다. 코드는 대문자로만 만든다.
    room = db.exec(select(Room).where(Room.invite_code == code.strip().upper())).first()
    if room is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "그 초대 코드의 방이 없습니다."},
        )
    return room


@router.get("/me", response_model=MeOut, summary="내 계정 보기")
def get_me(
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> MeOut:
    """로그인한 사람의 이름과 속한 방 목록.

    - 방이 하나도 없어도 200이고 `rooms`가 빈 목록입니다 (방 만들기 전 화면).
    - 로그인 안 했으면 401 `UNAUTHENTICATED`.
    """
    user = db.get(User, user_id)
    if user is None:
        # 쿠키는 있는데 사람이 없다 — 시드를 다시 넣은 뒤의 옛 쿠키
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHENTICATED", "message": "다시 로그인해 주세요."},
        )

    rooms = db.exec(
        select(Room)
        .join(Membership, Membership.room_id == Room.id)
        .where(Membership.user_id == user_id)
        .order_by(Membership.joined_at)
    ).all()
    return MeOut(
        user_id=user_id,
        name=user.name,
        rooms=[
            MyRoomOut(
                id=room.id, name=room.name, is_leader=room.leader_user_id == user_id
            )
            for room in rooms
        ],
    )


@router.get(
    "/rooms/by-invite-code/{code}",
    response_model=InvitePreviewOut,
    summary="초대 코드로 방 미리보기",
)
def preview_by_invite_code(
    code: str,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> InvitePreviewOut:
    """들어가기 전에 어떤 방인지 보여 줍니다. 방 이름과 인원만 내려갑니다.

    - 코드는 대소문자를 가리지 않습니다.
    - 없는 코드면 404 `NOT_FOUND`.
    """
    room = _room_by_code(db, code)
    assert room.id is not None
    return InvitePreviewOut(
        name=room.name,
        member_count=room.member_count,
        joined_count=joined_count(db, room.id),
    )


@router.post("/rooms/join", response_model=RoomOut, summary="초대 코드로 방 들어가기")
def join_room(
    body: JoinIn,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> RoomOut:
    """초대 코드로 팀원이 됩니다. 성공하면 방 정보를 그대로 돌려줍니다.

    - 이미 팀원이면 409 `ALREADY_MEMBER`.
    - 정원이 다 찼으면 409 `ROOM_FULL`.
    - 없는 코드면 404 `NOT_FOUND`.
    """
    room = _room_by_code(db, body.invite_code)
    assert room.id is not None

    already = db.exec(
        select(Membership.id).where(
            Membership.room_id == room.id, Membership.user_id == user_id
        )
    ).first()
    if already is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "ALREADY_MEMBER", "message": "이미 이 방의 팀원입니다."},
        )
    if joined_count(db, room.id) >= room.member_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "ROOM_FULL", "message": "팀원 수가 다 찼습니다."},
        )

    db.add(Membership(room_id=room.id, user_id=user_id))
    try:
        db.commit()
    except IntegrityError as exc:
        # 두 창에서 동시에 눌러 위 검사를 같이 통과한 경우. 유일 제약이 막는다.
        db.rollback()
        if _constraint(exc) == "uq_membership_room_user":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "code": "ALREADY_MEMBER",
                    "message": "이미 이 방의 팀원입니다.",
                },
            ) from exc
        raise
    return room_out(db, room, user_id)


@router.post(
    "/rooms",
    response_model=RoomOut,
    status_code=status.HTTP_201_CREATED,
    summary="방 만들기",
)
def create_room(
    body: RoomCreateIn,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> RoomOut:
    """새 팀플방을 만듭니다. 만든 사람이 팀장이 되고 초대 코드 6자리가 나옵니다.

    - 마감일이 시작일보다 앞서면 400 `INVALID_INPUT` (`field`: `due_date`).
    - 팀원 수는 2~6명. 벗어나면 400 `INVALID_INPUT` (`field`: `member_count`).
    """
    if body.start_date > body.due_date:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_INPUT",
                "field": "due_date",
                "message": "마감일은 시작일과 같거나 뒤여야 합니다.",
            },
        )

    for _ in range(INVITE_RETRIES):
        room = Room(
            name=body.name,
            description=body.description,
            start_date=body.start_date,
            due_date=body.due_date,
            eval_method=body.eval_method,
            member_count=body.member_count,
            invite_code=new_invite_code(),
            leader_user_id=user_id,
        )
        try:
            # 코드가 겹치면 이 방만 되돌리고 다시 뽑는다
            with db.begin_nested():
                db.add(room)
                db.flush()
        except IntegrityError as exc:
            if _constraint(exc) == "ix_room_invite_code":
                continue
            raise
        break
    else:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "INVITE_CODE_BUSY", "message": "잠시 후 다시 해 주세요."},
        )

    assert room.id is not None
    db.add(Membership(room_id=room.id, user_id=user_id))
    db.commit()
    db.refresh(room)
    return room_out(db, room, user_id)


@router.get("/rooms/{room_id}", response_model=RoomOut, summary="방 정보·팀원 보기")
def get_room(
    room_id: int,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> RoomOut:
    """팀 화면이 이것 하나로 그려집니다. 방 정보, 마감 디데이, 팀원 목록.

    - 팀원은 팀장이 맨 위, 나머지는 들어온 순서입니다.
    - 누적 양보는 숫자 없이 단계(`none`/`some`/`much`)로만 나갑니다.
    - 팀원이 아니거나 없는 방이면 403 `FORBIDDEN`.
    """
    require_member(db, room_id, user_id)
    room = db.get(Room, room_id)
    assert room is not None  # require_member가 없는 방도 403으로 막는다
    return room_out(db, room, user_id)
