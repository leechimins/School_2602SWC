"""온보딩 엔드포인트. 로그인부터 끝까지 실제 요청으로 본다.

conftest의 session 픽스처가 매 테스트마다 스키마를 다시 만들므로 시드는
없다. 필요한 사람만 테스트에서 만든다.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.main import app
from app.me.models import Preference
from app.shared.db import session_dep
from app.shared.models import User

API = "/api/v1"


@pytest.fixture(autouse=True)
def LLM을_끈다(monkeypatch: pytest.MonkeyPatch) -> None:
    """이 파일은 저장·검증만 본다. 다듬기는 tests/test_avoid.py가 본다.

    안 끄면 온보딩 테스트가 실제 모델을 부른다 — 네트워크가 없으면 깨지고,
    있으면 같은 입력에 다른 답이 와서 들쭉날쭉해진다.
    """
    monkeypatch.setenv("LLM_ENABLED", "false")


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
def 지수(session: Session) -> User:
    user = User(name="지수")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _login(client: TestClient, name: str = "지수") -> None:
    res = client.post(f"{API}/sessions", json={"name": name})
    assert res.status_code == 201, res.text


# ── 로그인 ──────────────────────────────────────────────────────────


def test_로그인하면_이름과_id가_온다(client: TestClient, 지수: User) -> None:
    res = client.post(f"{API}/sessions", json={"name": "지수"})
    assert res.status_code == 201
    assert res.json() == {"user_id": 지수.id, "name": "지수"}


def test_없는_이름으로는_로그인이_안_된다(client: TestClient, 지수: User) -> None:
    res = client.post(f"{API}/sessions", json={"name": "없는사람"})
    assert res.status_code == 404
    # 명세 권장 규칙 1 — message는 화면에 그대로 띄울 한국어 한 줄이다.
    assert res.json()["code"] == "NOT_FOUND"
    assert "팀원" in res.json()["message"]


def test_로그인_없이는_선호를_못_읽는다(client: TestClient) -> None:
    res = client.get(f"{API}/me/preferences")
    assert res.status_code == 401
    assert res.json()["code"] == "UNAUTHENTICATED"


def test_로그아웃하면_다시_401이_된다(client: TestClient, 지수: User) -> None:
    _login(client)
    assert client.get(f"{API}/me/preferences").status_code == 200

    assert client.delete(f"{API}/sessions").status_code == 204
    assert client.get(f"{API}/me/preferences").status_code == 401


# ── 온보딩 ──────────────────────────────────────────────────────────


def test_온보딩_전에도_200에_빈_값이_온다(client: TestClient, 지수: User) -> None:
    """404를 주지 않는다. 선호는 네 칸이 다 비어도 되는 값이다."""
    _login(client)
    res = client.get(f"{API}/me/preferences")
    assert res.status_code == 200
    assert res.json()["day_start_min"] is None
    assert res.json()["updated_at"] is None


def test_네_답이_분과_열거값으로_저장된다(client: TestClient, 지수: User) -> None:
    _login(client)
    res = client.post(
        f"{API}/me/onboarding/interpret",
        json={
            "day_start": {"hour12": 9, "ampm": "am", "minute": 0},
            "day_end": {"hour12": 6, "ampm": "pm", "minute": 0},
            "mode_pref": "online",
            "dayparts": ["afternoon", "evening"],
            "avoid_raw": "금요일 저녁은 피하고 싶어요",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["day_start_min"] == 540
    assert body["day_end_min"] == 1080
    assert body["mode_pref"] == "online"
    assert body["dayparts"] == ["afternoon", "evening"]
    assert body["avoid_raw"] == "금요일 저녁은 피하고 싶어요"
    assert body["updated_at"] is not None

    # 다시 읽어도 같다 — 응답만 그럴듯하고 저장이 안 되는 일을 막는다.
    assert client.get(f"{API}/me/preferences").json()["day_start_min"] == 540


def test_모델이_없으면_다듬은_문장도_구간도_비어_있다(
    client: TestClient, 지수: User
) -> None:
    """원문을 복사해 넣지 않는다.

    브리프가 "그대로 인용하지 않고 에이전트가 다듬어서"라고 적었다. 다듬지
    않은 말이 그대로 조율 발언으로 나가는 게 다듬기가 막으려는 일이라,
    모델이 못 돌면 차라리 비워 둔다. 구간도 마찬가지다 — 없는 구간으로
    점수를 매기면 엉뚱한 시간이 거절된다.
    """
    _login(client)
    body = client.post(
        f"{API}/me/onboarding/interpret",
        json={"avoid_raw": "금요일 저녁은 피하고 싶어요"},
    ).json()
    assert body["avoid_raw"] == "금요일 저녁은 피하고 싶어요"  # 원문은 남는다
    assert body["avoid_polished"] is None
    assert body["avoid_weekdays"] is None
    assert body["avoid_start_min"] is None
    assert body["avoid_end_min"] is None


def test_네_칸을_다_비워도_넘어간다(client: TestClient, 지수: User) -> None:
    """브리프: 필수 항목은 없습니다. 네 개를 다 비워도 다음으로 넘어갑니다."""
    _login(client)
    res = client.post(f"{API}/me/onboarding/interpret", json={})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["day_start_min"] is None
    assert body["day_end_min"] is None
    assert body["mode_pref"] is None
    assert body["dayparts"] is None
    assert body["avoid_raw"] is None


def test_온보딩은_네_칸을_전부_덮어쓴다(client: TestClient, 지수: User) -> None:
    """한 화면에서 한꺼번에 받으므로 안 고른 칸은 비움이 맞다."""
    _login(client)
    client.post(f"{API}/me/onboarding/interpret", json={"mode_pref": "offline"})

    res = client.post(f"{API}/me/onboarding/interpret", json={"dayparts": ["lunch"]})
    assert res.json()["mode_pref"] is None
    assert res.json()["dayparts"] == ["lunch"]


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ((6, "pm"), (9, "am")),  # 거꾸로
        ((9, "am"), (9, "am")),  # 같으면 가능한 시간이 0분이다
    ],
)
def test_시작이_끝보다_늦으면_400이_온다(
    client: TestClient, 지수: User, start: tuple, end: tuple
) -> None:
    _login(client)
    res = client.post(
        f"{API}/me/onboarding/interpret",
        json={
            "day_start": {"hour12": start[0], "ampm": start[1]},
            "day_end": {"hour12": end[0], "ampm": end[1]},
        },
    )
    assert res.status_code == 400
    assert res.json()["code"] == "INVALID_INPUT"
    # 명세가 "field로 어느 칸인지"를 요구한다. "body"로는 화면이 못 쓴다.
    assert res.json()["field"] == "day_start"


def test_12시간제_밖의_값은_400이_온다(client: TestClient, 지수: User) -> None:
    """422가 아니라 400 INVALID_INPUT이어야 한다 — 명세의 에러 표다."""
    _login(client)
    res = client.post(
        f"{API}/me/onboarding/interpret",
        json={"day_start": {"hour12": 13, "ampm": "am"}},
    )
    assert res.status_code == 400
    assert res.json()["code"] == "INVALID_INPUT"
    assert res.json()["field"] == "hour12"


# ── 내 조건 편집 (PATCH) ─────────────────────────────────────────────


def test_보낸_키만_바뀌고_나머지는_남는다(client: TestClient, 지수: User) -> None:
    _login(client)
    client.post(
        f"{API}/me/onboarding/interpret",
        json={
            "day_start": {"hour12": 9, "ampm": "am"},
            "day_end": {"hour12": 6, "ampm": "pm"},
            "mode_pref": "online",
        },
    )

    res = client.patch(f"{API}/me/preferences", json={"mode_pref": "offline"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mode_pref"] == "offline"
    assert body["day_start_min"] == 540  # 안 보냈으니 남아 있다
    assert body["day_end_min"] == 1080


def test_null을_보내면_지워진다(client: TestClient, 지수: User) -> None:
    """안 보냄과 null을 보냄이 다르다."""
    _login(client)
    client.post(f"{API}/me/onboarding/interpret", json={"mode_pref": "online"})

    res = client.patch(f"{API}/me/preferences", json={"mode_pref": None})
    assert res.json()["mode_pref"] is None


def test_원문을_고치면_다듬은_문장이_비워진다(
    client: TestClient, session: Session, 지수: User
) -> None:
    """다듬은 문장은 원문에 대한 것이다. 원문이 바뀌면 더 이상 그 말이 아니다."""
    _login(client)
    client.post(f"{API}/me/onboarding/interpret", json={"avoid_raw": "오전은 힘들어요"})

    # 에이전트가 다듬어 둔 상태를 손으로 만든다. 구간까지 차 있어야
    # "원문이 바뀌면 구간도 같이 비워지는지"를 볼 수 있다.
    pref = session.exec(select(Preference).where(Preference.user_id == 지수.id)).one()
    pref.avoid_polished = "오전에는 수업이 연달아 있어 어렵습니다"
    pref.avoid_weekdays = [0, 1, 2, 3, 4]
    pref.avoid_start_min = 9 * 60
    pref.avoid_end_min = 12 * 60
    session.add(pref)
    session.commit()

    res = client.patch(f"{API}/me/preferences", json={"avoid_raw": "저녁이 힘들어요"})
    assert res.json()["avoid_raw"] == "저녁이 힘들어요"
    assert res.json()["avoid_polished"] is None
    # 구간도 같이 비워진다. 안 비우면 "저녁이 힘들다"는 사람이 오전에
    # 벌점을 받는다.
    assert res.json()["avoid_weekdays"] is None
    assert res.json()["avoid_start_min"] is None


def test_한쪽만_보내도_합친_범위를_검사한다(client: TestClient, 지수: User) -> None:
    """PATCH는 한쪽만 올 수 있어서 저장된 값과 합친 뒤에 봐야 한다."""
    _login(client)
    client.post(
        f"{API}/me/onboarding/interpret",
        json={
            "day_start": {"hour12": 9, "ampm": "am"},
            "day_end": {"hour12": 6, "ampm": "pm"},
        },
    )

    # 끝만 8am으로 당기면 9am부터 8am까지가 된다.
    res = client.patch(
        f"{API}/me/preferences", json={"day_end": {"hour12": 8, "ampm": "am"}}
    )
    assert res.status_code == 400
    assert res.json()["code"] == "INVALID_INPUT"


def test_온보딩을_건너뛴_사람도_편집할_수_있다(client: TestClient, 지수: User) -> None:
    """건너뛰기로 행이 없는 상태에서 내 조건 화면에 바로 들어올 수 있다."""
    _login(client)
    res = client.patch(f"{API}/me/preferences", json={"mode_pref": "any"})
    assert res.status_code == 200, res.text
    assert res.json()["mode_pref"] == "any"


def test_남의_선호는_안_보인다(
    client: TestClient, session: Session, 지수: User
) -> None:
    민지 = User(name="민지")
    session.add(민지)
    session.commit()
    session.refresh(민지)
    session.add(Preference(user_id=민지.id, day_start_min=600))
    session.commit()

    _login(client, "지수")
    assert client.get(f"{API}/me/preferences").json()["day_start_min"] is None


def test_같은_한_줄을_다시_보내면_모델을_안_부른다(
    client: TestClient, session: Session, 지수: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """전에는 키가 오기만 하면 값이 같아도 다시 불렀다.

    화면이 객체 전체를 보내는 흔한 구조면 시간대만 바꿔도 모델을 기다린다 —
    키가 없거나 공급자가 느리면 최대 20초다(shared/llm.py TIMEOUT_SEC).
    """
    부른횟수 = {"n": 0}

    def 센다(raw: str | None):
        부른횟수["n"] += 1
        return None

    monkeypatch.setattr("app.me.router.avoid.interpret", 센다)
    _login(client, "지수")

    한줄 = {"avoid_raw": "금요일 저녁은 피하고 싶어요"}
    assert client.patch(f"{API}/me/preferences", json=한줄).status_code == 200
    assert 부른횟수["n"] == 1

    assert client.patch(f"{API}/me/preferences", json=한줄).status_code == 200
    assert 부른횟수["n"] == 1, "같은 값인데 또 불렀습니다"

    다른줄 = {"avoid_raw": "월요일 아침은 피하고 싶어요"}
    assert client.patch(f"{API}/me/preferences", json=다른줄).status_code == 200
    assert 부른횟수["n"] == 2, "바뀌었는데 안 불렀습니다"
