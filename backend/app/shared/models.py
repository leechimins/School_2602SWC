"""Room 도메인 — user · room · membership.

레인 표대로면 이 세 테이블은 B(장연우) 것이다. 그런데 A의 테이블 14개가
전부 이 셋으로 FK가 걸려서, 이게 없으면 A 쪽 create_all이 아예 돌지 않는다.
D1에 A가 막히지 않으려고 A가 먼저 만들어 뒀다.

이 파일은 B 것으로 넘긴다. 열을 더하거나 고칠 때 A에게 물어볼 필요 없다.
왜 이렇게 생겼는지는 db-설계.md §2 "설계 이유 (인계용)"에 적어 뒀다.

A가 읽는 것은 셋뿐이다. 이것만 미리 알려 주면 된다:
  - user.id
  - room.leader_user_id    (조율 시작이 팀장만이라 권한을 여기서 본다)
  - membership.yield_total (조율의 양보 차등)

아직 비어 있는 것: 로그인·세션(명세대로 세션 쿠키), 초대 코드 만드는 규칙,
member_count를 실제 인원과 맞추는 로직. 전부 Room 도메인이다.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.shared.base import ts


class User(SQLModel, table=True):
    # user는 Postgres 예약어다. SQLAlchemy가 "user"로 따옴표를 붙여 주므로
    # 코드에서는 문제없지만, psql에서 손으로 쓸 때는 SELECT * FROM "user"처럼
    # 따옴표가 필요하다.
    __tablename__ = "user"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=20, index=True)
    # 구글 계정 번호(ID 토큰의 sub). 구글로 로그인한 사람만 있다. 시드 4명은 null이고
    # 이름 로그인(POST /sessions)으로 들어온다. 이메일은 쓸 데가 없어 저장하지 않는다.
    google_sub: str | None = Field(default=None, max_length=255, unique=True)
    created_at: datetime = ts(auto_now=True)


class Room(SQLModel, table=True):
    __tablename__ = "room"
    __table_args__ = (
        CheckConstraint("start_date <= due_date", name="ck_room_period"),
        CheckConstraint("member_count > 0", name="ck_room_member_count"),
    )

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    description: str = Field(default="", max_length=500)
    start_date: date
    # 마감 디데이의 유일한 기준. 11/3에 단계·점검일·진행률을 다 없애서
    # 홈과 일정 화면의 "남은 날"이 이 한 칸에서 나온다.
    due_date: date
    eval_method: str = Field(max_length=50)
    member_count: int
    invite_code: str = Field(max_length=6, unique=True, index=True)
    # 팀장. 이 방에서 팀장인지를 보는 유일한 자리다.
    #
    # 방 만들기와 조율 시작이 팀장만이고, 명세 권장 규칙 4가 "권한은 서버가
    # 판단해 can_*로 내려줌"이라 그 값을 만들 때 이 열을 읽는다. 들어온
    # 요청이 팀장 것인지는 leader_user_id == 요청자 id로 끝난다.
    #
    # membership에 role 열을 따로 두지 않는 이유:
    #   - 한 팀에서 팀장이 바뀌지 않기로 했다. 그러면 "그때 누가 팀장이었나"를
    #     남길 일이 없어서 기록용으로 둘 이유가 사라진다.
    #   - 두 곳에 두면 서로 어긋날 수 있다(여기는 지수, membership은 민지).
    #   - NOT NULL이라 팀장이 정확히 한 명임을 DB가 보장한다. role 열로는
    #     둘이 leader가 되는 것을 막으려면 부분 인덱스를 또 걸어야 한다.
    # 나중에 팀장을 넘기거나 공동 팀장을 두기로 하면 그때 다시 생각한다.
    leader_user_id: int = Field(foreign_key="user.id", ondelete="CASCADE")
    created_at: datetime = ts(auto_now=True)


class Membership(SQLModel, table=True):
    __tablename__ = "membership"
    __table_args__ = (
        # 같은 사람이 한 방에 두 번 들어오는 것을 DB에서 막는다.
        UniqueConstraint("room_id", "user_id", name="uq_membership_room_user"),
        CheckConstraint("yield_total >= 0", name="ck_membership_yield_total"),
    )

    id: int | None = Field(default=None, primary_key=True)
    room_id: int = Field(foreign_key="room.id", ondelete="CASCADE", index=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    # 팀장인지는 room.leader_user_id 하나로만 본다. role 열을 두지 않는 이유:
    # 한 팀에서 팀장이 바뀌지 않기로 했으므로 기록용으로 남길 것이 없고,
    # 두 곳에 두면 서로 어긋날 수 있다. leader_user_id는 NOT NULL이라
    # 팀장이 정확히 한 명임을 DB가 보장하는데, role로는 둘이 leader가 되는
    # 것을 막으려면 부분 인덱스를 또 걸어야 한다.
    # 팀 화면의 "역할"(자료조사·발표·개발·디자인). 자유 입력이라 열거값이 아니다.
    part: str | None = Field(default=None, max_length=30)
    # 누적 양보 점수. yield_entry를 매번 합산하지 않으려고 둔 값이다.
    # A가 조율할 때마다 읽으므로 합계 쿼리로 두면 조율이 느려진다.
    # A가 회의 확정 시 같은 트랜잭션에서 올린다 — B는 이 열을 쓰지 않는다.
    yield_total: int = Field(default=0)
    joined_at: datetime = ts(auto_now=True)
