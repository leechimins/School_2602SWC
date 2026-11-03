"""테이블을 지우고 다시 만들고 시드를 넣는다.

    python -m tools.reset_db

마이그레이션 도구를 쓰지 않는 이유는 db-설계.md §0에 적혀 있다. 13일짜리에
Alembic은 과하고, 시연 데이터가 전부 시드에서 나오므로 지워도 잃을 게 없다.

다만 배포 DB에 사람이 넣은 데이터가 생긴 뒤부터는 이걸 쓸 수 없다.
그때부터는 손으로 ALTER TABLE을 쓴다.
"""

from __future__ import annotations

from sqlmodel import Session, SQLModel

from app.shared.db import create_all, engine, reset_schema
from tools.seed import seed


def main() -> None:
    target = engine()
    print(f"대상: {target.url.render_as_string(hide_password=True)}")

    # drop_all이 아니라 reset_schema다. 모델에서 뺀 테이블이 DB에 남아 있으면
    # drop_all은 그걸 모르고, 남은 테이블의 FK가 DROP TABLE을 막는다.
    reset_schema(target)
    print("지웠습니다.")

    create_all(target)
    print(f"테이블 {len(SQLModel.metadata.tables)}개를 만들었습니다.")

    with Session(target) as session:
        seed(session)
    print("시드를 넣었습니다.")


if __name__ == "__main__":
    main()
