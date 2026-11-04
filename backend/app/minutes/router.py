"""회의록 · 할 일 제안 · 할 일. 레인 B.

한 방 안의 일이라 prefix가 `/rooms/{room_id}`다. 엔드포인트는 각 이슈에서
채운다.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/rooms/{room_id}", tags=["minutes"])
