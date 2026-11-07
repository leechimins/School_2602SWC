"""시연 데이터.

브리프의 "시안에 쓸 예시 데이터"와 같게 맞춘다. 시연 화면과 시안이
어긋나지 않게 하려는 것이다. 디자인 쪽이 같은 이름·같은 날짜로 그린다.

가장 중요한 것: 현우의 yield_total = 3이고, 그 3이 서로 다른 회의 2건에서
나온다. 이게 없으면 2라운드에서 "현우는 지난 두 번의 회의에서 많이 맞춰
줬어요" — 시연의 핵심 대사가 안 나온다. 한 회의에 +3을 몰아넣으면
"두 번"이 거짓이 된다.

빈 테이블을 전제한다. tools/reset_db.py가 지우고 나서 부른다.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlmodel import Session

from app.demo.models import DemoState
from app.me.models import Preference, ScheduleItem
from app.meeting.models import Meeting, MeetingResponse, YieldEntry
from app.minutes.models import Minutes, MinutesItem, Task, TranscriptSegment
from app.shared.base import KST
from app.shared.enums import (
    Daypart,
    MeetingStatus,
    MinutesItemKind,
    MinutesStatus,
    Mode,
    Recurrence,
    ResponseState,
    ScheduleKind,
    ScheduleSource,
    TaskOrigin,
    TaskState,
    TranscriptMode,
)
from app.shared.models import Membership, Room, User

# 2026-11-03이 월요일이다. 그래서 10/27 = 월, 10/31 = 금.
MON, TUE, WED, THU, FRI = 0, 1, 2, 3, 4

INVITE_CODE = "T9K2QM"  # 시연마다 같아야 외워서 칠 수 있다


def at(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """aware(KST) 시각. naive를 만들지 않는다."""
    return datetime(year, month, day, hour, minute, tzinfo=KST)


def hm(hour: int, minute: int = 0) -> int:
    """자정부터 분. 13:00 → 780."""
    return hour * 60 + minute


def seed(session: Session) -> None:
    session.add(DemoState(id=1, now_at=None))

    # --- 사람 ---
    jisu = User(name="지수")
    minji = User(name="민지")
    hyunwoo = User(name="현우")
    seoyeon = User(name="서연")
    session.add_all([jisu, minji, hyunwoo, seoyeon])
    session.flush()  # id를 받는다

    # --- 방 ---
    # 시작일을 10/20으로 잡는 이유: 과거 회의 2건이 기간 안에 들어와야 한다.
    room = Room(
        name="서비스디자인 팀 프로젝트",
        description="학기 과제. 최종 발표와 시연까지 간다.",
        start_date=date(2026, 10, 20),
        due_date=date(2026, 12, 11),
        eval_method="최종 발표 + 시연",
        member_count=4,
        invite_code=INVITE_CODE,
        leader_user_id=jisu.id,
    )
    session.add(room)
    session.flush()

    # 팀장은 room.leader_user_id(지수)로만 정해진다. membership에 role 열이 없다.
    session.add_all(
        [
            Membership(room_id=room.id, user_id=jisu.id, part="자료조사"),
            Membership(room_id=room.id, user_id=minji.id, part="발표"),
            # 지난 두 번의 회의에서 맞춰 준 사람. 아래 yield_entry 2건의 합과 같다.
            Membership(
                room_id=room.id, user_id=hyunwoo.id, part="개발", yield_total=3
            ),
            Membership(room_id=room.id, user_id=seoyeon.id, part="디자인"),
        ]
    )

    # --- 선호 (온보딩 답 네 개) ---
    session.add_all(
        [
            Preference(
                user_id=jisu.id,
                day_start_min=hm(9),
                day_end_min=hm(22),
                mode_pref=Mode.ANY,
                dayparts=[Daypart.AFTERNOON],
            ),
            Preference(
                user_id=minji.id,
                day_start_min=hm(10),
                day_end_min=hm(21),
                mode_pref=Mode.OFFLINE,
                dayparts=[Daypart.AFTERNOON, Daypart.EVENING],
                avoid_raw="오전은 수업이 많아서 힘들어요",
                avoid_polished="오전에는 수업이 연달아 있어 어렵습니다",
                # 온보딩에서는 LLM이 이 셋을 뽑는다. 시드는 손으로 적는다.
                avoid_weekdays=[0, 1, 2, 3, 4],
                avoid_start_min=9 * 60,
                avoid_end_min=12 * 60,
            ),
            Preference(
                user_id=hyunwoo.id,
                day_start_min=hm(9),
                day_end_min=hm(18),
                mode_pref=Mode.ANY,
                dayparts=[Daypart.FORENOON, Daypart.AFTERNOON],
                avoid_raw="평일 저녁은 알바가 있어요",
                avoid_polished="평일 저녁에는 아르바이트가 있어 어렵습니다",
                avoid_weekdays=[0, 1, 2, 3, 4],
                avoid_start_min=17 * 60,
                avoid_end_min=22 * 60,
            ),
            Preference(
                user_id=seoyeon.id,
                day_start_min=hm(10),
                day_end_min=hm(23),
                mode_pref=Mode.ONLINE,
                dayparts=[Daypart.EVENING, Daypart.NIGHT],
            ),
        ]
    )

    # --- 시간표 ---
    semester = {"valid_from": date(2026, 9, 1), "valid_to": date(2026, 12, 20)}

    def klass(user_id: int, group: int, weekday: int, start: int, end: int, title: str):
        return ScheduleItem(
            user_id=user_id,
            group_id=group,
            source=ScheduleSource.EVERYTIME,
            kind=ScheduleKind.CLASS,
            title=title,
            recurrence=Recurrence.WEEKLY,
            weekday=weekday,
            start_min=start,
            end_min=end,
            **semester,
        )

    session.add_all(
        [
            klass(jisu.id, 101, TUE, hm(13), hm(14, 30), "서비스디자인"),
            klass(jisu.id, 102, THU, hm(10, 30), hm(12), "사용자조사"),
            # 민지는 수업이 많다. 오전이 거의 막혀 있어야 조율에서 이유가 선다.
            klass(minji.id, 201, MON, hm(10, 30), hm(12), "인터랙션"),
            klass(minji.id, 202, MON, hm(13), hm(14, 30), "시각디자인"),
            klass(minji.id, 203, TUE, hm(9), hm(12), "디자인사"),
            klass(minji.id, 204, WED, hm(10, 30), hm(12), "타이포그래피"),
            klass(minji.id, 205, THU, hm(13), hm(16), "프로젝트스튜디오"),
            klass(minji.id, 206, FRI, hm(9), hm(10, 30), "색채학"),
            klass(hyunwoo.id, 301, WED, hm(9), hm(12), "자료구조"),
            klass(seoyeon.id, 401, WED, hm(13), hm(16), "UX기초"),
            klass(seoyeon.id, 402, FRI, hm(13), hm(14, 30), "모션그래픽"),
        ]
    )

    # 현우의 알바. 평일 저녁 18~22시. 묶음 하나(group_id=302)에 요일 다섯 행이다.
    session.add_all(
        [
            ScheduleItem(
                user_id=hyunwoo.id,
                group_id=302,
                source=ScheduleSource.MANUAL,
                kind=ScheduleKind.PARTTIME,
                title="편의점 알바",
                recurrence=Recurrence.WEEKLY,
                weekday=weekday,
                start_min=hm(18),
                end_min=hm(22),
                **semester,
            )
            for weekday in (MON, TUE, WED, THU, FRI)
        ]
    )

    # --- 지난 회의 2건 ---
    # 양보 점수가 서로 다른 회의에서 나와야 "지난 두 번"이 참이 된다.
    members = [jisu, minji, hyunwoo, seoyeon]

    first = Meeting(
        room_id=room.id,
        topic="역할 나누기",
        start_at=at(2026, 10, 27, 16),
        end_at=at(2026, 10, 27, 18),
        mode=Mode.OFFLINE,
        status=MeetingStatus.DONE,
        rationale="현우의 알바 시작 직전이지만, 네 사람이 다 비는 시간이 "
        "이 두 시간뿐이었습니다.",
        confirmed_at=at(2026, 10, 25, 21, 10),
    )
    second = Meeting(
        room_id=room.id,
        topic="중간 발표 자료 나누기",
        start_at=at(2026, 10, 31, 10),
        end_at=at(2026, 10, 31, 12),
        mode=Mode.ONLINE,
        status=MeetingStatus.DONE,
        rationale="금요일 오전은 민지의 수업이 끝난 뒤라 가장 덜 불편했습니다.",
        confirmed_at=at(2026, 10, 29, 20, 40),
    )
    session.add_all([first, second])
    session.flush()

    for meeting in (first, second):
        session.add_all(
            [
                MeetingResponse(
                    meeting_id=meeting.id,
                    user_id=member.id,
                    state=ResponseState.ACCEPTED,
                    responded_at=meeting.confirmed_at,
                )
                for member in members
            ]
        )

    session.add_all(
        [
            # 불편 4(많이) → +2
            YieldEntry(
                room_id=room.id,
                meeting_id=first.id,
                user_id=hyunwoo.id,
                points=2,
                discomfort=4,
                reason="알바 시작 직전이라 많이 불편한 시간을 맞춰 줘서 +2",
            ),
            # 불편 2(조금) → +1
            YieldEntry(
                room_id=room.id,
                meeting_id=second.id,
                user_id=hyunwoo.id,
                points=1,
                discomfort=2,
                reason="평소보다 이른 오전을 맞춰 줘서 +1",
            ),
        ]
    )

    _seed_minutes_and_tasks(session, room, second, first, jisu, minji, hyunwoo, seoyeon)

    session.commit()


def _seed_minutes_and_tasks(
    session: Session,
    room: Room,
    meeting: Meeting,
    earlier: Meeting,
    jisu: User,
    minji: User,
    hyunwoo: User,
    seoyeon: User,
) -> None:
    """레인 B 시드. 지난 회의(10/31)의 회의록과 그 회의에서 나온 할 일.

    기준 시점은 시연 시계의 오늘, 2026-11-10이다. 기한이 그보다 앞서고
    끝나지 않은 할 일이 하나 있어야 늦음 뱃지가 보이고, 담당자 없는 할
    일이 있어야 "담당자 없음" 묶음이 보인다. 그 전 회의(10/27)에서 나와
    10/31 회의에서 끝난 일이 하나 있어야 회의록의 "회의에서 끝난 일"이 보인다.
    """
    held = at(2026, 10, 31, 12)  # 회의가 끝난 시각 이후로 모든 기록을 찍는다

    # --- 원문 ---
    lines = [
        (jisu, "오늘은 중간 발표 자료를 누가 어디까지 맡을지 정하죠."),
        (minji, "발표는 제가 할게요. 슬라이드 초안은 다음 주 목요일까지 가능해요."),
        (hyunwoo, "저는 프로토타입 화면을 구현할게요. 알바 때문에 평일 저녁은 어려워요."),
        (seoyeon, "디자인 시안은 제가 볼게요. 발표 대본은 아직 맡을 사람이 없어요."),
        (jisu, "사용자 인터뷰 정리는 제가 이번 주말까지 끝낼게요."),
        (None, "리허설 일정은 다음 회의에서 다시 이야기해요."),
    ]
    session.add_all(
        [
            TranscriptSegment(
                meeting_id=meeting.id,
                seq=seq,
                speaker_user_id=speaker.id if speaker else None,
                text=text,
                created_at=held,
            )
            for seq, (speaker, text) in enumerate(lines)
        ]
    )
    meeting.transcript_mode = TranscriptMode.MANUAL

    # --- 회의록 ---
    minutes = Minutes(
        meeting_id=meeting.id,
        headline="중간 발표 자료를 역할별로 나눔",
        status=MinutesStatus.DONE,
        created_at=held,
    )
    session.add(minutes)
    session.flush()

    items = [
        (MinutesItemKind.DECISION, "발표는 민지, 프로토타입 구현은 현우가 맡는다."),
        (MinutesItemKind.DECISION, "사용자 인터뷰 정리는 지수가 이번 주말까지 끝낸다."),
        (MinutesItemKind.DISCUSSION, "현우는 평일 저녁 알바가 있어 회의는 낮이 낫다."),
        (MinutesItemKind.PENDING, "발표 대본을 누가 쓸지 정하지 못했다."),
        (MinutesItemKind.PENDING, "최종 발표 리허설 일정."),
    ]
    session.add_all(
        [
            MinutesItem(minutes_id=minutes.id, kind=kind, seq=seq, text=text)
            for seq, (kind, text) in enumerate(items)
        ]
    )

    # --- 확정된 할 일 ---
    def confirmed(
        title, due, assignee, state, *, by, origin=TaskOrigin.AI, src=meeting, done_in=None
    ):
        return Task(
            room_id=room.id,
            meeting_id=src.id if src else None,
            done_meeting_id=done_in.id if done_in else None,
            title=title,
            due_date=due,
            assignee_user_id=assignee.id if assignee else None,
            state=state,
            origin=origin,
            confirmed=True,
            confirmed_by=by.id,
            confirmed_at=held,
            created_at=held,
        )

    session.add_all(
        [
            # 기한(11/8)이 오늘(11/10)보다 앞서고 끝나지 않았다 → 늦음
            confirmed(
                "사용자 인터뷰 정리", date(2026, 11, 8), jisu, TaskState.DOING, by=jisu
            ),
            confirmed(
                "발표 슬라이드 초안", date(2026, 11, 13), minji, TaskState.TODO, by=jisu
            ),
            confirmed(
                "프로토타입 화면 구현",
                date(2026, 11, 15),
                hyunwoo,
                TaskState.BLOCKED,
                by=jisu,
            ),
            # 10/27 회의에서 나와 10/31 회의에서 "끝났다"고 한 일 → 회의에서 끝난 일
            confirmed(
                "참고 사례 조사",
                date(2026, 11, 5),
                jisu,
                TaskState.DONE,
                by=jisu,
                src=earlier,
                done_in=meeting,
            ),
            # 담당자 없음은 오류가 아니라 정상 시작 상태다
            confirmed("발표 대본 작성", date(2026, 11, 17), None, TaskState.TODO, by=jisu),
            # 직접 추가한 할 일. 출처 회의가 없다.
            confirmed(
                "대면 회의 장소 예약",
                date(2026, 11, 12),
                jisu,
                TaskState.TODO,
                by=jisu,
                origin=TaskOrigin.MANUAL,
                src=None,
            ),
        ]
    )

    # --- 확정 전 제안(AI 제안). 할 일 목록에는 나오지 않는다 ---
    def proposal(title, due, assignee=None):
        return Task(
            room_id=room.id,
            meeting_id=meeting.id,
            title=title,
            due_date=due,
            assignee_user_id=assignee.id if assignee else None,
            state=TaskState.TODO,
            origin=TaskOrigin.AI,
            confirmed=False,
            created_at=held,
        )

    session.add_all(
        [
            # 회의록에 "제가 볼게요"가 분명해서 담당자가 채워진 제안
            proposal("디자인 시안 정리", date(2026, 11, 14), seoyeon),
            # 담당자가 불분명해 비어 있는 제안
            proposal("최종 발표 리허설 일정 잡기", date(2026, 11, 18)),
            proposal("시연 영상 촬영 계획", None),
        ]
    )
