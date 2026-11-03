"""온보딩과 내 조건 — /me/preferences.

조율 엔진이 읽는 재료를 사람이 넣는 유일한 길이다. 지금까지는 시드만
채웠다.

service.py를 따로 두지 않았다. 지금 하는 일이 "피커를 분으로 바꿔 upsert"
한 줄씩이라 층을 하나 더 만들면 읽을 게 늘기만 한다. 조율 엔진에서 순서가
길어지면 그때 가른다(backend/README.md의 파일 배치).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.me.models import Preference
from app.me.schemas import OnboardingIn, PreferenceOut, PreferencePatch
from app.shared.auth import current_user_id
from app.shared.base import real_now
from app.shared.db import session_dep

router = APIRouter(prefix="/me", tags=["me"])


def _load(db: Session, user_id: int) -> Preference | None:
    return db.exec(select(Preference).where(Preference.user_id == user_id)).first()


def _save(db: Session, pref: Preference) -> PreferenceOut:
    """updated_at을 직접 넣는 이유: ts(auto_now=True)는 행을 만들 때만 채운다.

    여기서 real_now()를 쓰고 demo_clock을 쓰지 않는다. 이 값은 판정에 쓰이지
    않고(README 지킬 것 1번은 판정용 "지금"에 대한 규칙이다) 같은 테이블의
    created_at들과 같은 시계를 봐야 읽을 때 덜 헷갈린다.
    """
    pref.updated_at = real_now()
    db.add(pref)
    db.commit()
    db.refresh(pref)
    return PreferenceOut.model_validate(pref, from_attributes=True)


def _reject_reversed_range(pref: Preference) -> None:
    """저장된 값과 합친 뒤에 본다. PATCH가 한쪽만 보낼 수 있어서다.

    DB에도 같은 CHECK가 있다(ck_preference_day_range). 여기서 먼저 막는 건
    화면에 그대로 띄울 한국어 한 줄을 주려는 것뿐이다 — CHECK가 걸리면
    500이 나간다.
    """
    if pref.day_start_min is None or pref.day_end_min is None:
        return
    if pref.day_start_min >= pref.day_end_min:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_INPUT",
                "field": "day_start",
                "message": "가능한 시작 시각이 끝 시각보다 앞이어야 합니다.",
            },
        )


@router.post("/onboarding/interpret", response_model=PreferenceOut)
def interpret_onboarding(
    body: OnboardingIn,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> PreferenceOut:
    """온보딩 네 답을 받아 저장하고, 저장된 값을 돌려준다.

    명세는 이걸 "해석하기"로 적었지만 저장까지 한다. 온보딩 화면에는 확인
    단계가 없고 버튼이 하나뿐이라(네 질문을 한 화면에, 건너뛰기), 해석과
    저장을 나누면 두 번째 호출이 실패할 때 반쯤 저장된 상태가 남는다.

    네 칸을 전부 덮어쓴다. 보낸 것만 반영하는 건 PATCH 쪽이다 — 온보딩은
    네 개를 한 화면에서 한꺼번에 받으므로 안 고른 칸은 "비움"이 맞다.
    """
    pref = _load(db, user_id) or Preference(user_id=user_id)

    pref.day_start_min = body.day_start.to_minutes() if body.day_start else None
    pref.day_end_min = body.day_end.to_minutes() if body.day_end else None
    pref.mode_pref = body.mode_pref
    pref.dayparts = body.dayparts
    pref.avoid_raw = body.avoid_raw
    # LLM 공급자를 아직 안 골랐다. 원문을 복사해 넣지 않는 이유는
    # schemas.PreferenceOut의 주석에 적어 뒀다.
    pref.avoid_polished = None

    _reject_reversed_range(pref)
    return _save(db, pref)


@router.get("/preferences", response_model=PreferenceOut)
def read_preferences(
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> PreferenceOut:
    """온보딩을 아직 안 한 사람에게도 200을 준다. 전부 null인 객체가 나간다.

    404를 주면 내 조건 화면이 "없음"과 "실패"를 가려야 한다. 선호는 네 칸이
    다 비어도 되는 값이라 빈 객체가 정확한 답이다.
    """
    pref = _load(db, user_id)
    if pref is None:
        return PreferenceOut()
    return PreferenceOut.model_validate(pref, from_attributes=True)


@router.patch("/preferences", response_model=PreferenceOut)
def update_preferences(
    body: PreferencePatch,
    user_id: int = Depends(current_user_id),
    db: Session = Depends(session_dep),
) -> PreferenceOut:
    """내 조건 화면의 편집. 보낸 키만 반영한다.

    "안 보냄"과 "null을 보냄"을 model_fields_set으로 가른다. 안 보낸 칸은
    그대로 두고, null을 보내면 지운다.
    """
    pref = _load(db, user_id) or Preference(user_id=user_id)
    sent = body.model_fields_set

    if "day_start" in sent:
        pref.day_start_min = body.day_start.to_minutes() if body.day_start else None
    if "day_end" in sent:
        pref.day_end_min = body.day_end.to_minutes() if body.day_end else None
    if "mode_pref" in sent:
        pref.mode_pref = body.mode_pref
    if "dayparts" in sent:
        pref.dayparts = body.dayparts
    if "avoid_raw" in sent:
        pref.avoid_raw = body.avoid_raw
        # 원문이 바뀌면 다듬은 문장은 더 이상 그 말이 아니다. 비워서
        # 에이전트가 다시 다듬게 한다.
        pref.avoid_polished = None

    _reject_reversed_range(pref)
    return _save(db, pref)
