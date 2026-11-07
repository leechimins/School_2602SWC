"""외부 연동이 주고받는 모양. Field의 description은 Swagger에 그대로 보인다."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

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
