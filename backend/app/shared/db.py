"""DB 접속과 테이블 생성.

접속 정보는 .env의 DATABASE_URL 하나로만 받는다. 코드에 박지 않는 이유는
매니지드(Neon·Supabase)로 옮길 때 이 한 줄만 바꾸면 되게 하려는 것이다.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import Engine, text
from sqlmodel import SQLModel, create_engine

load_dotenv()

_engine: Engine | None = None


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"{name}이 없습니다. .env.example을 .env로 복사하세요.\n"
            "없을 때 조용히 SQLite로 떨어지지 않게 일부러 여기서 멈춥니다 — "
            "그러면 부분 인덱스와 배열이 없는 DB에서 테스트가 통과해 버립니다."
        )
    return value


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True)


def engine() -> Engine:
    """개발용 엔진. 처음 부를 때 만든다.

    함수로 둔 이유: import 시점에 만들면 DATABASE_URL 없이 테스트만 돌릴 수
    없다. 테스트는 TEST_DATABASE_URL로 자기 엔진을 만든다.
    """
    global _engine
    if _engine is None:
        _engine = make_engine(_require("DATABASE_URL"))
    return _engine


def register_models() -> None:
    """SQLModel.metadata에 테이블을 등록한다.

    import하지 않은 모듈의 테이블은 create_all이 만들지 않는다. 그래서
    여기가 유일한 등록 지점이다. 새 도메인을 만들면 한 줄을 더한다.
    """
    import app.demo.models  # noqa: F401
    import app.me.models  # noqa: F401
    import app.meeting.models  # noqa: F401
    import app.notice.models  # noqa: F401
    import app.shared.models  # noqa: F401


def create_all(target: Engine | None = None) -> None:
    register_models()
    SQLModel.metadata.create_all(target or engine())


def reset_schema(target: Engine | None = None) -> None:
    """DB를 빈 상태로 되돌린다.

    SQLModel.metadata.drop_all을 쓰지 않는다. 그건 지금 모델에 있는 테이블만
    지우므로, 모델에서 테이블을 빼면(11/3의 scheduling_note) 그 테이블이 DB에
    남아 FK로 다른 테이블을 붙잡고 DROP TABLE이 실패해 reset이 아예 막힌다.

    스키마를 통째로 지우면 모델에 없는 것까지 사라지므로 그 일이 없다.
    마이그레이션 도구를 안 쓰기로 한 선택(db-설계.md §0)이 성립하려면
    이 길이 항상 열려 있어야 한다.
    """
    eng = target or engine()
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
