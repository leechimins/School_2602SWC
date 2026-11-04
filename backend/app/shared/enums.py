"""열거값. 화면 용어와 1:1로 맞춘다.

A·B 두 레인이 같이 읽는 파일이다. 값을 더하거나 고치면 db-설계.md와
API 명세에도 같이 반영한다. 여기 있는 값이 그대로 JSON에 나가므로
화면에 보이는 한국어 문구는 프론트가 매핑한다.
"""

from __future__ import annotations

from enum import StrEnum


# Role(leader/member) 열거값을 두지 않는다. 한 팀에서 팀장이 바뀌지 않기로
# 했으므로 팀장은 room.leader_user_id 하나로 정해지고, membership에 role 열이
# 없다. 그 밖의 권한은 아직 안 정해졌다(브리프 "아직 안 정해진 것").


class Mode(StrEnum):
    """대면·비대면. `any`는 조율 조건과 선호에만 쓴다.

    확정된 회의는 둘 중 하나로 정해지므로 meeting.mode에는 `any`가 들어가지
    않는다. CHECK로 막아 둔다.
    """

    OFFLINE = "offline"
    ONLINE = "online"
    ANY = "any"


class SchedulingStatus(StrEnum):
    """조율의 상태. 화면 세 갈래와 1:1이다.

    agreed    → 회의 일정 조율 확인 화면
    needs_pick → 3라운드 안에 합의 실패, 후보 2~3개를 사람이 고른다
    no_common  → 전원 가능한 시간이 없다, 1명 불참안
    """

    RUNNING = "running"
    AGREED = "agreed"
    NEEDS_PICK = "needs_pick"
    NO_COMMON = "no_common"
    FAILED = "failed"


class MeetingStatus(StrEnum):
    """회의의 상태.

    proposed가 곧 "회의안"이다. 별도 테이블을 두지 않고 이 상태로 둔 이유는
    db-설계.md §0 "두 가지 이름, 한 행"에 적어 뒀다. 전원 수락하면 행을
    옮기지 않고 confirmed로 바꾼다.
    """

    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    DONE = "done"
    CANCELLED = "cancelled"


class ResponseState(StrEnum):
    """수락·거절. 회의안이 만들어질 때 팀원 수만큼 pending으로 깔린다.

    그래야 "누가 아직 안 답했는지"를 이름으로 보여 줄 수 있다.
    """

    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"


class ScheduleSource(StrEnum):
    """시간표 한 칸이 어디서 왔나."""

    EVERYTIME = "everytime"
    GOOGLE = "google"
    MANUAL = "manual"


class ScheduleKind(StrEnum):
    """시간표 한 칸이 무엇인가.

    appointment는 제목을 비우고 화면에 "바쁨"으로만 나간다. 구글 캘린더에서
    온 개인 약속의 제목을 팀원에게 보여 주지 않는다.
    """

    CLASS = "class"
    PARTTIME = "parttime"
    APPOINTMENT = "appointment"


class Recurrence(StrEnum):
    """주간 반복인가 한 번인가.

    weekly는 weekday·start_min·end_min을 쓰고, once는 start_at·end_at을 쓴다.
    """

    WEEKLY = "weekly"
    ONCE = "once"


class Daypart(StrEnum):
    """온보딩 질문 3의 여섯 갈래. 여러 개를 고를 수 있다."""

    MORNING = "morning"
    FORENOON = "forenoon"
    LUNCH = "lunch"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"


class SpeakerKind(StrEnum):
    """조율 발언을 누가 했나. 화면에서 둘이 구분되게 그린다."""

    JUDGE = "judge"
    MEMBER = "member"


class TranscriptMode(StrEnum):
    """회의 기록을 받아적었나 직접 썼나.

    받아적기가 기본이고 직접쓰기가 보조다. meeting 테이블의 열이지만
    채우는 쪽은 B(Record)다.
    """

    STT = "stt"
    MANUAL = "manual"


class NotificationKind(StrEnum):
    """알림 카드의 종류.

    앞의 셋이 브리프의 알림 3종이다. late·blocked는 챙기라는 알림이고
    done만 좋은 소식이라, 뱃지가 둘을 구분해야 한다.

    late·blocked·done은 할 일에서 나오므로 B가 shared의 emit()을 불러
    만든다. B가 notification 테이블에 직접 쓰지는 않는다.
    """

    LATE = "late"
    BLOCKED = "blocked"
    DONE = "done"
    MEETING_SOON = "meeting_soon"
    MEETING_PROPOSED = "meeting_proposed"
    MEETING_CONFIRMED = "meeting_confirmed"


class CalendarKind(StrEnum):
    """연동의 종류. 에브리타임은 수업, 구글 캘린더는 개인 약속을 담는다."""

    EVERYTIME = "everytime"
    GOOGLE = "google"


class LinkStatus(StrEnum):
    """연동이 지금 읽히나. failed여도 직접 입력으로 계속 진행된다."""

    OK = "ok"
    FAILED = "failed"


class MinutesStatus(StrEnum):
    """회의록 요약의 상태. 원문을 먼저 보이고 요약 자리만 비워 두는 동안이 summarizing."""

    SUMMARIZING = "summarizing"
    DONE = "done"
    FAILED = "failed"


class MinutesItemKind(StrEnum):
    """회의록 요약 분류. 브리프의 "결정 / 논의 / 보류"."""

    DECISION = "decision"
    DISCUSSION = "discussion"
    PENDING = "pending"


class TaskState(StrEnum):
    """할 일 상태 네 개. 진행률 숫자는 없다."""

    TODO = "todo"
    DOING = "doing"
    BLOCKED = "blocked"
    DONE = "done"


class YieldLevel(StrEnum):
    """누적 양보 단계. 남의 누적 점수는 숫자 대신 이 단계로만 나간다.

    화면 문구: 아직 없음 / 조금 맞춰 줌 / 많이 맞춰 줌. 경계값은 아직 팀
    합의 전이라 app/room/service.py의 상수 한 곳에만 둔다.
    """

    NONE = "none"
    SOME = "some"
    MUCH = "much"


class TaskOrigin(StrEnum):
    """할 일이 어디서 왔나. ai인 동안은 "AI 제안" 표시가 붙는다."""

    AI = "ai"
    MANUAL = "manual"
