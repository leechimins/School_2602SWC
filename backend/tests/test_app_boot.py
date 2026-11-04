"""앱을 띄우는 것만으로 쓸 수 있는 상태가 되는지.

**이 파일만 새 프로세스를 띄운다.** 다른 테스트와 같은 프로세스에서 보면
의미가 없어서다 — pytest는 모든 테스트 파일을 한 프로세스에서 돌리므로,
어떤 파일 하나가 `app.minutes.models`를 import하면(test_notice_api.py가
실제로 그렇게 한다) 그 프로세스 전체에 남아 문제가 숨는다.

실제 서버(`uvicorn app.main:app`)에는 conftest도 create_all도 없다. 그래서
"테스트는 통과하는데 서버만 터지는" 일이 생긴다. 11/4에 실제로 그랬다 —
notification.task_id가 가리키는 task(레인 B)를 아무도 import하지 않아서,
알림을 읽음 처리하는 순간 NoReferencedTableError로 터졌다.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent


def _in_fresh_process(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        capture_output=True,
        text=True,
    )


def test_앱만_띄워도_테이블이_전부_등록된다() -> None:
    """도메인을 넘는 FK가 풀리려면 모든 모델이 metadata에 있어야 한다.

    FK는 `foreign_key="task.id"`처럼 글자로 적혀 있고, SQLAlchemy가 저장할
    때 그 이름을 metadata에서 찾는다. 찾지 못하면 그 테이블과 상관없는
    저장까지 전부 막힌다 — 테이블 사이 저장 순서를 정하려고 FK 지도를
    통째로 그리기 때문이다.
    """
    done = _in_fresh_process(
        "import app.main\n"
        "from sqlmodel import SQLModel\n"
        "print(len(SQLModel.metadata.tables))\n"
    )
    assert done.returncode == 0, done.stderr
    assert int(done.stdout.strip()) == 22


def test_앱만_띄워도_FK_지도가_그려진다() -> None:
    """11/4에 터진 그 단계. DB 없이 확인한다.

    sorted_tables가 테이블을 저장 순서대로 세우려고 FK를 전부 따라간다 —
    ORM이 commit할 때 하는 일과 같다. 이름 하나만 못 찾아도 거기서 멈추고,
    그러면 그 테이블과 상관없는 저장까지 전부 막힌다.

    configure_mappers()로는 안 된다. 확인해 봤는데 FK 이름을 풀지 않고
    통과해서, 고장난 상태에서도 초록불이 뜬다.
    """
    done = _in_fresh_process(
        "import app.main\n"
        "from sqlmodel import SQLModel\n"
        "SQLModel.metadata.sorted_tables\n"
    )
    assert done.returncode == 0, done.stderr
