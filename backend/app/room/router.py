"""Room — 내 계정, 방, 초대 코드.

경로가 `/me`와 `/rooms/*`로 갈려 prefix를 두지 않는다. 엔드포인트는
Room API 이슈에서 채운다.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["room"])
