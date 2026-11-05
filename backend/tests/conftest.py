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
from sqlalchemy import Engine, text
from sqlmodel import Session, SQLModel

from app.main import app
from app.meeting import runner
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


@pytest.fixture(autouse=True)
def LLM을_끈다(monkeypatch: pytest.MonkeyPatch) -> None:
    """테스트는 네트워크를 안 탄다.

    조율 라운드가 뒷단으로 가면서 POST 한 번에 모델이 불린다. 끄지 않으면
    거의 모든 테스트가 진짜 Gemini를 부르고, 키가 없으면 타임아웃만큼
    멈춘다. 모델을 보는 테스트는 자기가 다시 켠다(test_avoid.py).
    """
    monkeypatch.setenv("LLM_ENABLED", "false")


@pytest.fixture(scope="session")
def schema(test_engine: Engine) -> Engine:
    """테이블은 세션에 한 번만 만든다."""
    reset_schema(test_engine)
    create_all(test_engine)
    return test_engine


@pytest.fixture
def session(schema: Engine) -> Iterator[Session]:
    """매 테스트마다 행만 비운다. 테이블은 그대로 둔다.

    테스트가 제약 위반을 일부러 일으켜 트랜잭션이 더러워지므로 롤백으로
    버티지 않는다. 그렇다고 테스트마다 스키마를 드롭하면 안 된다 — psycopg가
    서버에 준비해 둔 구문이 사라진 테이블을 가리켜서, 테스트가 많아질수록
    relation does not exist와 already exists가 뒤섞여 터진다. 11/5에 그걸로
    40건이 났다.

    TRUNCATE는 테이블을 남기므로 그 일이 없고, DDL 23개가 한 문장으로 줄어
    훨씬 빠르다. RESTART IDENTITY로 id를 1부터 다시 세어 room/1을 가정하는
    테스트가 그대로 돈다.

    **조율 라운드를 스레드 대신 같은 자리에서 돌린다.** 운영에서는 뒷단
    스레드가 자기 세션을 열지만(meeting/runner.py), 테스트는 세션 하나를
    공유하고 테스트가 끝나면 행이 통째로 지워져 뒤늦게 도는 스레드가
    엉뚱한 데서 터진다. 세션은 운영과 똑같이 따로 연다 — 아래를 보라.
    스레드 자체를 보는 테스트는 runner.start를 직접 부른다(test_runner.py).
    """
    with schema.begin() as conn:
        tables = ", ".join(f'"{name}"' for name in SQLModel.metadata.tables)
        conn.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
    with Session(schema) as db:
        with pytest.MonkeyPatch.context() as mp:
            # 뒷단 루프에게 **자기 세션**을 준다. 요청 세션을 같이 쓰면 한
            # 세션이 두 군데서 add/commit을 받아 같은 발언이 두 번 들어간다
            # (uq_utterance_seq로 터진다). 운영도 자기 세션을 쓴다.
            mp.setattr("app.shared.db.background_session", lambda: Session(schema))
            mp.setattr("app.meeting.runner.start", runner.run_to_end)
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
