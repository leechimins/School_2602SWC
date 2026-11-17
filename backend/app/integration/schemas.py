"""외부 연동이 주고받는 모양. Field의 description은 Swagger에 그대로 보인다."""

from __future__ import annotations

from datetime import datetime

from pydantic import model_validator
from sqlmodel import Field, SQLModel

from app.integration.timetable import TermState
from app.shared.enums import CalendarKind, LinkStatus


class GoogleConnectIn(SQLModel):
    """구글 팝업에서 받은 인증 코드.

    프론트는 Google Identity Services의 `initCodeClient`를 `ux_mode: "popup"`,
    `scope: "https://www.googleapis.com/auth/calendar.readonly"`,
    `access_type: "offline"`, `prompt: "consent"`로 열고, 콜백의 `code`를 그대로 보낸다.
    """

    code: str = Field(min_length=1, max_length=1000, description="구글이 준 인증 코드. 한 번만 쓸 수 있음")


class EverytimeConnectIn(SQLModel):
    """에브리타임에서 시간표를 공유하면 나오는 링크."""

    url: str = Field(
        min_length=1,
        max_length=300,
        description="공유 링크. 예: https://everytime.kr/@AbCd1234 (https:// 없이도 됨)",
    )


class IntegrationOut(SQLModel):
    """연동 상태. 토큰은 담지 않는다."""

    kind: CalendarKind = Field(description="연동 종류")
    connected: bool = Field(description="연결돼 있나")
    status: LinkStatus | None = Field(
        description="ok면 읽히는 중, failed면 다시 연결해야 함. 연결 안 했으면 null"
    )
    account: str | None = Field(
        description="구글은 연결한 계정, 에브리타임은 공유 링크(everytime.kr/@아이디). 본인에게만 보임"
    )
    last_synced_at: datetime | None = Field(description="마지막으로 읽은 시각")
    imported_count: int = Field(
        description="구글은 '바쁨'으로 잡힌 약속 수, 에브리타임은 들어온 수업(과목) 수"
    )
    term: str | None = Field(
        default=None,
        description="에브리타임만. 읽어 온 시간표의 학기(예: '2026년 2학기'). 지난 학기 링크인지 알려 줄 때 쓴다",
    )
    term_state: TermState | None = Field(
        default=None,
        description=(
            "에브리타임만. 오늘 기준으로 그 학기가 current(이번 학기)·past(지난 학기)·"
            "upcoming(다음 학기를 미리 넣음). 학기를 모르면 null. "
            "past여도 저장은 되고 조율에서 안 셀 뿐이라, 화면에서 이번 학기 링크를 넣으라고 안내한다"
        ),
    )


# ── 시간표 캡처 (#66) ───────────────────────────────────────────────


class CaptureClass(SQLModel):
    """캡처에서 읽은(또는 사람이 고친) 수업 한 칸. 요일 하나에 한 칸."""

    title: str = Field(min_length=1, max_length=60, description="과목명")
    weekday: int = Field(ge=0, le=6, description="0=월 … 6=일")
    start_min: int = Field(ge=0, le=1435, description="시작. 0시부터 분, 5분 단위")
    end_min: int = Field(ge=5, le=1440, description="끝. 0시부터 분, 5분 단위")

    @model_validator(mode="after")
    def _order(self) -> CaptureClass:
        self.title = " ".join(self.title.split())
        if not self.title:
            raise ValueError("과목명을 채워 주세요.")
        if self.start_min >= self.end_min:
            raise ValueError("끝나는 시간을 시작보다 늦게 맞춰 주세요.")
        return self


class CapturePreviewOut(SQLModel):
    """AI가 캡처에서 읽은 수업. 저장하지 않았다 — 사람이 확인·수정해 확정해야 들어간다."""

    classes: list[CaptureClass] = Field(description="읽은 수업. 못 읽었으면 빈 목록")
    year: int | None = Field(default=None, description="캡처 위쪽 학기 글씨의 연도. 확정할 때 그대로 돌려보낸다")
    semester: str | None = Field(default=None, description="'1'·'2' 또는 그 밖의 학기 글자. 확정할 때 그대로 돌려보낸다")
    term: str | None = Field(default=None, description="화면에 띄울 학기(예: '2024년 2학기')")


class CaptureSaveIn(SQLModel):
    """사람이 확인·수정한 수업 목록. 이전 에브리타임 수업을 이것으로 바꾼다."""

    classes: list[CaptureClass] = Field(min_length=1, max_length=50, description="넣을 수업")
    year: int | None = Field(
        default=None,
        ge=2000,
        le=2100,
        description="미리보기의 year. 없으면 오늘(시연 시계)이 속한 학기로 본다",
    )
    semester: str | None = Field(default=None, max_length=10, description="미리보기의 semester")
