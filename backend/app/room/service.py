"""Room 계산 — 양보 단계, 초대 코드, 응답 조립.

라우터에서 뺀 이유: RoomOut은 방 정보·방 만들기·들어가기 셋이 같이
돌려주는 모양이라 조립을 한 곳에 둔다.
"""

from __future__ import annotations

import secrets

from sqlmodel import Session, func, select

from app.room.schemas import MemberOut, RoomOut
from app.shared import demo_clock
from app.shared.enums import YieldLevel
from app.shared.models import Membership, Room, User

# 누적 양보 단계의 경계. 팀 합의 전 임시값이다. 바꾸면 여기만 바뀐다.
# 시드의 현우(3)가 "많이 맞춰 줌"으로 보여야 2라운드 대사와 맞는다.
YIELD_SOME_FROM = 1
YIELD_MUCH_FROM = 3

# 0/O, 1/I/L을 뺐다. 외워서 치거나 불러 줄 때 헷갈린다.
INVITE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
INVITE_LENGTH = 6


def yield_level(total: int) -> YieldLevel:
    if total >= YIELD_MUCH_FROM:
        return YieldLevel.MUCH
    if total >= YIELD_SOME_FROM:
        return YieldLevel.SOME
    return YieldLevel.NONE


def new_invite_code() -> str:
    return "".join(secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_LENGTH))


def joined_count(db: Session, room_id: int) -> int:
    return db.exec(
        select(func.count()).select_from(Membership).where(Membership.room_id == room_id)
    ).one()


def room_out(db: Session, room: Room, viewer_id: int) -> RoomOut:
    assert room.id is not None
    rows = db.exec(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.room_id == room.id)
        .order_by(Membership.joined_at, Membership.id)
    ).all()

    today = demo_clock.now(db).date()
    members = [
        MemberOut(
            user_id=user.id,
            name=user.name,
            part=membership.part,
            is_leader=user.id == room.leader_user_id,
            is_me=user.id == viewer_id,
            yield_level=yield_level(membership.yield_total),
        )
        for membership, user in rows
    ]
    # 팀장이 맨 위. 나머지는 들어온 순서.
    members.sort(key=lambda m: not m.is_leader)

    return RoomOut(
        id=room.id,
        name=room.name,
        description=room.description,
        start_date=room.start_date,
        due_date=room.due_date,
        d_day=(room.due_date - today).days,
        eval_method=room.eval_method,
        member_count=room.member_count,
        joined_count=len(members),
        invite_code=room.invite_code,
        leader_user_id=room.leader_user_id,
        members=members,
        can_start_scheduling=viewer_id == room.leader_user_id,
    )
