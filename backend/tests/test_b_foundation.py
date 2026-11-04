"""레인 B 기반: conftest의 공용 client · login · seeded가 도는지 본다.

B의 API 테스트는 이 셋으로 시작한다. 엔드포인트가 생기면 이 파일의
방식을 그대로 따라 쓴다.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

API = "/api/v1"


def test_로그인_없이는_보호된_API가_401이다(client: TestClient, seeded) -> None:
    res = client.get(f"{API}/me/preferences")

    assert res.status_code == 401
    assert res.json()["code"] == "UNAUTHENTICATED"


def test_로그인_헬퍼로_시드_팀원이_로그인한다(client: TestClient, seeded, login) -> None:
    login("현우")

    res = client.get(f"{API}/me/preferences")

    assert res.status_code == 200


def test_시드에_없는_이름은_404이고_에러는_code_message_모양이다(
    client: TestClient, seeded
) -> None:
    res = client.post(f"{API}/sessions", json={"name": "없는사람"})

    assert res.status_code == 404
    assert set(res.json()) == {"code", "message"}
