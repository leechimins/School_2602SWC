"""테스트 DB.

SQLite로 테스트하지 않는다. 부분 인덱스(한 방에 running 조율 하나)와
배열(preference.dayparts)이 SQLite에 없어서, 돌려 봐야 검증이 거짓이 된다.
같은 Docker Postgres의 teamagent_test 데이터베이스를 쓴다.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from dotenv import load_dotenv
from sqlalchemy import Engine
from sqlmodel import Session

from app.shared.db import create_all, make_engine, reset_schema

load_dotenv()


@pytest.fixture(scope="session")
def test_engine() -> Engine:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.fail(
            "TEST_DATABASE_URL이 없습니다. .env.example을 .env로 복사하세요."
        )
    return make_engine(url)


@pytest.fixture
def session(test_engine: Engine) -> Iterator[Session]:
    """매 테스트마다 테이블을 다시 만든다.

    테스트가 제약 위반을 일부러 일으키므로 트랜잭션이 더러워진다. 롤백으로
    버티는 대신 통째로 다시 만드는 쪽이 읽기 쉽다 — 테이블이 22개뿐이라
    충분히 빠르다.
    """
    reset_schema(test_engine)
    create_all(test_engine)
    with Session(test_engine) as db:
        yield db
