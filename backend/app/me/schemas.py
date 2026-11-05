"""온보딩과 내 조건이 주고받는 모양. table=True가 없는 모델만 있다.

여기가 입력 검사의 유일한 실제 방어선 중 하나다. SQLModel은 table=True인
클래스에서 Pydantic 검사를 끄므로(backend/README.md 지킬 것 3번) 모델 클래스에
기대면 안 된다. 이 파일의 클래스들은 table=True가 없어서 검사가 그대로 돈다.

DB의 CHECK가 나머지 절반이다. 둘 다 있어야 한다 — 여기서 막는 것은 친절한
400 메시지를 주기 위한 것이고, CHECK는 어느 경로로 들어와도 막기 위한 것이다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from sqlmodel import Field, SQLModel

from app.shared.enums import Daypart, Mode


class Hour12(SQLModel):
    """화면의 시각 피커 한 칸 — 숫자 + 오전·오후.

    자유 입력을 받지 않는다. 그래서 한국어 시각 파서가 없다.

    minute이 0·30뿐인 이유: 브리프가 회의 길이를 30분 단위로 정했으므로
    가능 시간도 30분 단위면 충분하고, 피커 선택지가 둘로 줄어 화면이 간단해진다.
    """

    hour12: int = Field(ge=1, le=12)
    ampm: Literal["am", "pm"]
    minute: Literal[0, 30] = 0

    def to_minutes(self) -> int:
        """자정부터 분. 540 = 9:00.

        12시가 유일하게 까다롭다 — 12am은 0시, 12pm은 12시다. % 12가 12를
        0으로 만들어 주고, pm이면 12를 더한다.
        """
        return (self.hour12 % 12 + (12 if self.ampm == "pm" else 0)) * 60 + self.minute


class OnboardingIn(SQLModel):
    """온보딩 질문 네 개의 답.

    넷 다 비어도 된다. 브리프: "필수 항목은 없습니다. 네 개를 다 비워도
    다음으로 넘어갑니다." 비면 빈칸 찾기가 그 조건을 안 쓴다.

    day_start < day_end를 여기서 검사하지 않는다. 라우터가 저장된 값과 합친
    뒤에 본다(PreferencePatch와 같은 길). 여기서 하면 Pydantic 오류의 loc이
    ("body",)라서 명세가 요구하는 "어느 칸인지"를 못 알려 준다.
    """

    # 질문 1 — 보통 몇 시부터 몇 시까지 가능해요? (한 질문이 두 값을 낸다)
    day_start: Hour12 | None = None
    day_end: Hour12 | None = None
    # 질문 2 — 대면과 비대면 중 어느 쪽이 편해요?
    mode_pref: Mode | None = None
    # 질문 3 — 언제가 좋아요? (여러 개)
    dayparts: list[Daypart] | None = None
    # 질문 4 — 꼭 피하고 싶은 시간대가 있어요?
    avoid_raw: str | None = Field(default=None, max_length=200)


class PreferencePatch(SQLModel):
    """내 조건 화면의 편집. 보낸 키만 반영한다.

    "안 보냄"과 "null을 보냄"이 다르다. 안 보낸 칸은 그대로 두고, null을
    보내면 지운다. 라우터가 model_fields_set으로 가른다.

    여기서 day_start < day_end를 검사하지 않는 이유: 한쪽만 보낼 수 있어서
    저장된 값과 합친 뒤에야 알 수 있다. 라우터가 합친 결과로 검사한다.
    """

    day_start: Hour12 | None = None
    day_end: Hour12 | None = None
    mode_pref: Mode | None = None
    dayparts: list[Daypart] | None = None
    avoid_raw: str | None = Field(default=None, max_length=200)


class PreferenceOut(SQLModel):
    """내 조건 화면과 조율이 읽는 모양.

    시각은 자정부터 분으로 내려간다 — 화면이 피커로 되돌리는 쪽이 서버가
    "9:00"처럼 문자열을 만드는 것보다 어긋날 데가 적다.
    """

    day_start_min: int | None = None
    day_end_min: int | None = None
    mode_pref: Mode | None = None
    dayparts: list[Daypart] | None = None
    avoid_raw: str | None = None
    # 질문 4를 에이전트가 다듬은 문장. LLM 공급자를 아직 안 골라서 지금은 늘
    # null이다. 원문을 복사해 넣지 않는다 — 브리프가 "그대로 인용하지 않고
    # 에이전트가 다듬어서"라고 적었으므로, 복사하면 조율이 사람 말을 그대로
    # 읊는다. 빈 칸이 "아직 안 다듬었다"를 정확히 말한다.
    avoid_polished: str | None = None
    # 같은 한 줄에서 뽑은 구간. 점수에 쓰이는 건 이 셋이다. 못 뽑으면 셋 다
    # None이고 그때는 avoid_polished만 쓰인다(발언에만, 점수에는 안 들어감).
    avoid_weekdays: list[int] | None = None
    avoid_start_min: int | None = None
    avoid_end_min: int | None = None
    # 아직 온보딩을 안 한 사람은 행이 없어서 null이다.
    updated_at: datetime | None = None
