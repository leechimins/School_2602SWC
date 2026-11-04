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
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session

from app.main import app
from app.shared.db import create_all, make_engine, reset_schema, session_dep
from tools.seed import seed

load_dotenv()

API = "/api/v1"


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


# ── API 테스트 공용 (레인 B) ─────────────────────────────────────────
# 레인 A의 테스트 파일은 같은 이름의 client를 파일 안에 따로 갖고 있다.
# pytest는 파일 안의 픽스처를 conftest보다 먼저 쓰므로 서로 부딪치지 않는다.


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    """라우터가 테스트 DB를 쓰게 바꿔치기한다.

    같은 세션을 넘기는 이유: 테스트가 만든 행을 요청이 봐야 하고, 요청이
    저장한 행을 테스트가 봐야 한다.
    """
    app.dependency_overrides[session_dep] = lambda: session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def login(client: TestClient):
    """이름으로 로그인하는 함수. 쿠키는 client가 들고 있는다."""

    def _login(name: str = "지수") -> None:
        res = client.post(f"{API}/sessions", json={"name": name})
        assert res.status_code == 201, res.text

    return _login


@pytest.fixture
def seeded(session: Session) -> Session:
    """시연 시드가 들어간 DB. 팀원 4명과 방, 회의록, 할 일이 있다."""
    seed(session)
    return session
