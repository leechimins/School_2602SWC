"""배포 DB 주소. Render가 주는 postgresql://를 psycopg(3)로 읽는지."""

from app.shared.db import make_engine


def test_postgresql_주소는_psycopg로_연다() -> None:
    eng = make_engine("postgresql://u:p@host:5432/db")
    assert eng.url.drivername == "postgresql+psycopg"
    assert eng.url.host == "host"


def test_드라이버를_적은_주소는_그대로() -> None:
    assert make_engine("postgresql+psycopg://u:p@host/db").url.drivername == "postgresql+psycopg"
