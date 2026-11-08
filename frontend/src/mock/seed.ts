import { withJosa } from '../lib/korean.ts'
import type { Id, IsoDate, IsoDateTime, MeetingMode } from '../types/common.ts'
import type { Minutes, MeetingStatus } from '../types/meeting.ts'
import type { Preferences, ScheduleSource } from '../types/me.ts'
import type { AgentLogEntry, NoticeKind } from '../types/notification.ts'
import type { YieldLevel } from '../types/room.ts'
import type { ResponseState, SchedulingStatus } from '../types/scheduling.ts'
import type { TaskStatus } from '../types/task.ts'

// 시연 데이터. 디자인 브리프 "시안에 쓸 예시 데이터"와 시안10의 DATA를 그대로 옮겼다.
// 이 값은 서버의 DB 역할이라 보는 사람과 상관없는 원본만 담는다. 화면에 줄 모양(내 점수, can_*)은 mock/views.ts가 만든다.
// SEED는 직접 바꾸지 않는다. 저장소는 항상 structuredClone(SEED)로 시작한다(목업 버그 ④).

export const SEED_VERSION = 9 // 서버 시드(backend/tools/seed.py)로 바꾸고 알림을 저장하는 모양으로 바꿨다. 8은 내 조건(prefs)·주간 일정(scheduleItems)을 붙였다. 7은 할 일에 "필요 없어 보이는 일"(unneeded)을 붙였다. 6은 doneMeetingId. 3은 사람 수락·거절을 뺐던 판이라 건너뛴다

/** 사람 ID는 여기서 한 번만 정한다. 화면 코드에 'minji' 같은 값을 쓰지 않는다 */
export const USER = {
  jisu: 'u-jisu',
  minji: 'u-minji',
  hyunwoo: 'u-hyunwoo',
  seoyeon: 'u-seoyeon',
} as const

/** 시연 화면(/demo)에 휴대폰이 없는 팀원. 답할 사람이 없으니 회의안이 나오면 바로 수락한다(목 모드만) */
export const OFFSTAGE: readonly Id[] = [USER.hyunwoo, USER.seoyeon]

export const ROOM_ID: Id = 'room-1'

export type SeedMember = {
  id: Id
  name: string
  yieldTotal: number // 누적 양보 점수. 화면에는 단계로만 나간다(views.ts yieldLevelOf, 서버 membership.yield_total)
  note: string // 시연 설정 메모 (화면에 나오지 않음)
}

export type SeedTask = {
  id: Id
  title: string
  dueDate: IsoDate | null
  assigneeId: Id | null
  status: TaskStatus
  blockedReason: string | null
  meetingId: Id | null // 출처 회의. null = 직접 추가
  confirmedBy: Id | null
  confirmedAt: IsoDateTime | null
  doneMeetingId: Id | null // 회의에서 끝났다고 말해 완료로 바뀐 회의. 회의록의 "회의에서 끝난 일"에 보인다
  dismissed: boolean // "삭제"한 할 일. 목록에서 빠진다
  /** 회의에서 안 해도 된다고 한 일(회의록 "필요 없어 보이는 일"). kept = 그래도 두기로 함. 서버에는 없는 목록이라 목에서만 쓴다 */
  unneeded: { meetingId: Id; why: string; kept: boolean } | null
}

export type SeedSuggestion = {
  id: Id
  meetingId: Id
  title: string
  dueDate: IsoDate | null
  assigneeId: Id | null
}

export type SeedMeeting = {
  id: Id
  topic: string
  startAt: IsoDateTime
  endAt: IsoDateTime
  mode: MeetingMode
  status: MeetingStatus
  transcript: { speakerId: Id | null; text: string }[] // 직접 쓰기는 말한 사람이 없다
  minutes: Minutes | null
}

/** 조율 발언 원본. score는 그 시간의 불편 점수(1~5)이고 본인에게만 숫자로 보인다 */
export type SeedUtterance =
  | { kind: 'appeal'; round: number; who: Id; text: string }
  | { kind: 'answer'; round: number; who: Id; text: string; answer: '수락' | '거절'; score: number }
  | {
      kind: 'judge'
      round: number
      text: string
      slot: { startAt: IsoDateTime; endAt: IsoDateTime; mode: MeetingMode }
      yieldChanges: { who: Id; from: YieldLevel; to: YieldLevel }[]
    }

export type SeedScheduling = {
  id: Id
  topic: string
  windowStart: IsoDateTime
  windowEnd: IsoDateTime
  durationMin: number
  mode: MeetingMode | '상관없음'
  status: SchedulingStatus
  script: SeedUtterance[]
  result: ScenarioResult // 대본이 끝나면 나올 회의안의 바탕
  meetingId: Id | null // 조율이 끝나 나온 회의. 사람이 거절해 다시 도는 동안은 null
}

/** 수락·거절할 때 남긴 한 줄과, 에이전트가 그 말로 바꾼 선호 */
export type SeedFeedback = { text: string; change: string | null; undone: boolean }

/** 조율이 낸 회의의 사람별 부담과 응답 */
export type SeedProposal = {
  meetingId: Id
  schedulingId: Id | null // 이 회의안을 낸 조율. 거절로 회의가 취소돼도 과정 화면으로 돌아갈 수 있게. 조율 없이 잡힌 회의는 null
  settled: boolean
  rationale: string
  gets: Id | null // 이번에 양보 점수를 받는 사람
  getsFrom: YieldLevel // 그 사람의 조율 당시 누적 단계. 확정되면 한 단계 오른다
  absent: Id | null // 불참안에서 빠진 사람
  burdens: { userId: Id; score: number; reason: string }[]
  responses: Record<Id, ResponseState> // 응답할 사람(서버 meeting_response). 여기 없는 사람은 이 회의에서 빠진다
  feedback: Record<Id, SeedFeedback>
}

/** 알림 한 장(서버 notification). 서버처럼 일이 생길 때 사람마다 한 장씩 쌓는다(actions.ts emit) */
export type SeedNotice = {
  id: Id
  seq: number // 같은 시각이면 나중에 생긴 것이 위
  userId: Id // 받는 사람
  kind: NoticeKind
  reason: string
  taskId: Id | null
  meetingId: Id | null
  dedupe: string // 같은 사람에게 같은 키는 한 번만(서버 dedupe_key)
  createdAt: IsoDateTime
  read: boolean
}

/** 내 일정 한 줄(매주 반복). 요일마다 한 줄이고 같은 묶음(groupId)은 한 일정이다(백엔드 schedule_item) */
export type SeedScheduleItem = {
  id: Id
  userId: Id
  groupId: number
  title: string | null // 구글에서 온 약속은 제목이 없다
  kind: 'class' | 'event'
  source: ScheduleSource
  weekday: number // 0=월 … 6=일
  startMin: number // 자정부터 분
  endMin: number
}

export type DemoState = {
  version: number
  clockNow: IsoDateTime // 시연 시계. 앱의 "지금"은 이 값 하나다
  room: {
    id: Id
    name: string
    description: string
    startDate: IsoDate
    dueDate: IsoDate
    inviteCode: string
    memberCount: number
    leaderId: Id
  }
  members: SeedMember[]
  tasks: SeedTask[]
  suggestions: SeedSuggestion[]
  meetings: SeedMeeting[]
  schedulings: SeedScheduling[]
  proposals: SeedProposal[]
  notices: SeedNotice[]
  agentLog: AgentLogEntry[]
  yieldRecords: { id: Id; meetingLabel: string; userId: Id; why: string }[]
  prefs: Record<Id, Preferences> // 없으면 아직 온보딩 전(전부 빈 값)
  scheduleItems: SeedScheduleItem[]
  nextSeq: number // 새로 만드는 항목의 ID 번호
}

const hour = (h: number) => h * 60
/** 자정부터 분. 13:30 → hm(13, 30) */
const hm = (h: number, m = 0) => h * 60 + m
const item = (
  id: Id, userId: Id, groupId: number, title: string | null, kind: SeedScheduleItem['kind'],
  source: ScheduleSource, weekday: number, startMin: number, endMin: number,
): SeedScheduleItem => ({ id, userId, groupId, title, kind, source, weekday, startMin, endMin })

/** 에브리타임 공유 링크로 들어오는 수업(시연용). 누가 불러와도 이 네 과목이 들어온다 */
export const DEMO_EVERYTIME_CLASSES: Omit<SeedScheduleItem, 'id' | 'userId' | 'groupId'>[] = [
  { title: '디자인사고', kind: 'class', source: 'everytime', weekday: 0, startMin: hour(10), endMin: hour(12) },
  { title: '자료구조', kind: 'class', source: 'everytime', weekday: 2, startMin: hour(13), endMin: hour(16) },
  { title: '통계학', kind: 'class', source: 'everytime', weekday: 3, startMin: hour(10), endMin: hour(12) },
  { title: '영어회화', kind: 'class', source: 'everytime', weekday: 4, startMin: hour(10), endMin: hour(12) },
]

/** 구글 캘린더를 켜면 들어오는 약속(시연용). 제목 없이 "일정"으로만 보인다 */
export const DEMO_GOOGLE_EVENTS: Omit<SeedScheduleItem, 'id' | 'userId' | 'groupId'>[] = [
  { title: null, kind: 'event', source: 'google', weekday: 1, startMin: hour(12), endMin: hour(13) },
  { title: null, kind: 'event', source: 'google', weekday: 6, startMin: hour(14), endMin: hour(17) },
]

const { jisu, minji, hyunwoo, seoyeon } = USER

const task = (t: Partial<SeedTask> & Pick<SeedTask, 'id' | 'title' | 'dueDate' | 'assigneeId'>): SeedTask => ({
  status: '시작 전',
  blockedReason: null,
  meetingId: null,
  confirmedBy: null,
  confirmedAt: null,
  doneMeetingId: null,
  dismissed: false,
  unneeded: null,
  ...t,
})

/** 대본이 끝나면 나오는 회의안의 바탕. 회의 ID·응답은 조율이 끝날 때 붙는다 */
export type ScenarioResult = Omit<SeedProposal, 'meetingId' | 'schedulingId' | 'settled' | 'responses' | 'feedback'>

/**
 * 시연 조율 대본: 팀장이 "조율 시작"을 누르면 목 서버가 이 대본을 그대로 다시 돌린다(실서버에서는 AI가 만든다).
 * 팀장이 처음 조율을 시작하면 이 대본이 돈다.
 */
export const DEMO_SCENARIO: { script: SeedUtterance[]; result: ScenarioResult } = {
  // 11/7 흐름: 개인 에이전트가 원하는 시간을 어필 → 판단 에이전트가 그중 하나를 고름 → 개인 에이전트가 수락·거절(거절은 이유만).
  // 거절이 있으면 거절당한 시간을 낸 에이전트만 새 시간을 내고(어필 발언은 없다. 백엔드와 같다) 다음 라운드에서 판단이 다시 고른다. 최대 3라운드.
  // 에이전트가 모두 수락하면 사람 4명이 수락·거절한다(전원 수락 → 확정, 거절 → 3라운드까지 다시 조율: rerunScenario)
  script: [
    { kind: 'appeal', round: 1, who: jisu, text: '저는 목요일 오후가 제일 좋아요. 그 시간에는 수업이 없어요.' },
    { kind: 'appeal', round: 1, who: hyunwoo, text: '저는 수요일 오후가 제일 좋아요. 평일 저녁은 알바가 있어 어려워요.' },
    { kind: 'appeal', round: 1, who: minji, text: '저는 수요일 오후가 좋아요. 오전에는 수업이 연달아 있어 어려워요.' },
    { kind: 'appeal', round: 1, who: seoyeon, text: '저는 저녁 비대면이 제일 좋아요. 이동이 없어서요.' },
    {
      kind: 'judge', round: 1, yieldChanges: [],
      text: '네 분이 낸 시간 중에서 지수가 낸 목요일 13:00–15:00, 대면을 고릅니다. 팀 전체로는 가장 덜 불편한 시간이에요.',
      slot: { startAt: '2026-11-19T13:00:00+09:00', endAt: '2026-11-19T15:00:00+09:00', mode: '대면' },
    },
    { kind: 'answer', round: 1, who: jisu, answer: '수락', score: 1, text: '좋아요. 지수는 이 시간에 수업이 없어요.' },
    { kind: 'answer', round: 1, who: hyunwoo, answer: '거절', score: 4, text: '어렵습니다. 알바 끝나고 바로라 이동이 빠듯해요.' },
    { kind: 'answer', round: 1, who: minji, answer: '수락', score: 2, text: '괜찮아요. 수업이 끝나고 바로지만 맞출 수 있어요. 다만 금요일 저녁은 개인 일정이 있어 어려워요.' },
    { kind: 'answer', round: 1, who: seoyeon, answer: '수락', score: 2, text: '가능해요. 다만 서연은 비대면을 더 좋아해요.' },
    {
      kind: 'judge', round: 2,
      yieldChanges: [
        { who: hyunwoo, from: '많이 맞춰 줌', to: '많이 맞춰 줌' },
        { who: minji, from: '아직 없음', to: '조금 맞춰 줌' },
      ],
      text: '거절당한 목요일 오후를 냈던 지수가 목요일 19시 비대면을 새로 냈지만, 그 시간은 현우가 알바라 어려워요. 현우가 지난 두 번 많이 맞춰 줘서 이번엔 현우 쪽을 먼저 챙길게요. 현우·민지가 낸 수요일 16:00–18:00, 비대면을 고릅니다. 대신 민지가 조금 맞춰 주게 됩니다.',
      slot: { startAt: '2026-11-18T16:00:00+09:00', endAt: '2026-11-18T18:00:00+09:00', mode: '비대면' },
    },
    { kind: 'answer', round: 2, who: minji, answer: '수락', score: 3, text: '수업 바로 뒤라 조금 빠듯하지만 괜찮아요.' },
    { kind: 'answer', round: 2, who: hyunwoo, answer: '수락', score: 1, text: '좋아요. 알바가 19시부터라 여유 있게 끝나요.' },
    { kind: 'answer', round: 2, who: jisu, answer: '수락', score: 1, text: '좋아요. 지수도 이 시간은 비어 있어요.' },
    { kind: 'answer', round: 2, who: seoyeon, answer: '수락', score: 1, text: '비대면이라 더 좋아요.' },
  ],
  /** 대본이 끝나면 나오는 회의안. 응답은 모두 대기로 시작한다 */
  result: {
    rationale: '현우가 지난 두 번 많이 맞춰 줘서 이번엔 현우 쪽을 먼저 챙겼어요. 대신 민지가 조금 맞춰 주게 됩니다.',
    gets: minji,
    getsFrom: '아직 없음',
    absent: null,
    burdens: [
      { userId: minji, score: 3, reason: '수업 바로 뒤예요' },
      { userId: jisu, score: 1, reason: '선호 시간대 안이에요' },
      { userId: hyunwoo, score: 1, reason: '알바 전까지 여유가 있어요' },
      { userId: seoyeon, score: 1, reason: '비대면이라 이동이 없어요' },
    ],
  },
}

/**
 * 사람이 합의안을 거절했을 때 이어 도는 라운드(백엔드 rerun과 같은 모양): 거절당한 수요일 오후는 후보에서 빠지고,
 * 그 시간을 냈던 현우·민지의 에이전트만 새 시간을 낸다(어필 발언 없음). 판단 에이전트가 거절 이유를 듣고 다시 고른다.
 */
export function rerunScenario(
  round: number,
  declinerName: string,
  reason: string | null,
  jisuYield: { from: YieldLevel; to: YieldLevel }, // 이번에 맞춰 주는 지수의 누적 단계 변화
): { script: SeedUtterance[]; result: ScenarioResult } {
  const who = withJosa(declinerName, '이/가')
  return {
    script: [
      {
        kind: 'judge', round, yieldChanges: [{ who: jisu, ...jisuYield }],
        text: `${who} 수요일 16:00–18:00을 거절했어요. "${reason ?? '그 시간은 어렵다고 했어요'}" 그 시간을 냈던 현우·민지가 새로 낸 금요일 14:00–16:00, 비대면을 고릅니다. 대신 지수가 조금 맞춰 주게 됩니다.`,
        slot: { startAt: '2026-11-20T14:00:00+09:00', endAt: '2026-11-20T16:00:00+09:00', mode: '비대면' },
      },
      { kind: 'answer', round, who: jisu, answer: '수락', score: 2, text: '금요일 오후엔 수업이 하나 있지만, 끝나고 바로 들어갈 수 있어요.' },
      { kind: 'answer', round, who: hyunwoo, answer: '수락', score: 1, text: '좋아요. 금요일엔 알바가 없어요.' },
      { kind: 'answer', round, who: minji, answer: '수락', score: 1, text: '좋아요. 저녁 일정 전이라 괜찮아요.' },
      { kind: 'answer', round, who: seoyeon, answer: '수락', score: 1, text: '비대면이라 좋아요.' },
    ],
    result: {
      rationale: `${who} 수요일 오후를 거절해서, 그 시간을 냈던 현우·민지의 새 시간으로 다시 잡았어요. 대신 지수가 조금 맞춰 주게 됩니다.`,
      gets: jisu,
      getsFrom: jisuYield.from,
      absent: null,
      burdens: [
        { userId: jisu, score: 2, reason: '수업 끝나고 바로예요' },
        { userId: hyunwoo, score: 1, reason: '알바가 없는 날이에요' },
        { userId: minji, score: 1, reason: '저녁 일정 전이에요' },
        { userId: seoyeon, score: 1, reason: '비대면이라 이동이 없어요' },
      ],
    },
  }
}

/**
 * 시연 받아적기 대본: 일정 탭의 "지금 회의 받아적기"로 회의를 열면 이 말들이 한 줄씩 받아적힌다(실서버에서는 음성 인식).
 * 정리하면 아래 요약과 할 일 제안이 나온다. 담당자는 회의에서 "제가 할게요"처럼 분명히 말한 것만 채운다.
 */
export const DEMO_RECORDING: {
  topic: string
  lines: { who: Id; text: string }[]
  minutes: Omit<Minutes, 'headline' | 'status'>
  suggestions: Omit<SeedSuggestion, 'id' | 'meetingId'>[]
} = {
  topic: '발표 순서 정하기',
  lines: [
    { who: jisu, text: '구성안 보고 발표 순서를 정해요.' },
    { who: minji, text: '도입이랑 문제 정의는 제가 이어서 할게요. 금요일까지 대본 써 올게요.' },
    { who: seoyeon, text: '화면 설명은 제가 할게요.' },
    { who: hyunwoo, text: '시연은 제가 맡을게요. 시연 영상도 일요일까지 찍어 둘게요.' },
    { who: jisu, text: '리허설은 다음 주 월요일에 한 번 해요.' },
    { who: minji, text: '리허설 장소는 아직 못 정했어요. 누가 알아봐 주면 좋겠어요.' },
  ],
  minutes: {
    decisions: ['발표 순서: 도입·문제 정의 민지 → 화면 설명 서연 → 시연 현우', '리허설은 11/16(월)'],
    discussions: ['시연 영상을 미리 찍어 두기'],
    pendings: ['리허설 장소: 알아볼 사람 정하기'],
  },
  suggestions: [
    { title: '도입·문제 정의 대본', dueDate: '2026-11-13', assigneeId: minji },
    { title: '시연 영상 촬영', dueDate: '2026-11-15', assigneeId: hyunwoo },
    { title: '화면 설명 대본', dueDate: '2026-11-14', assigneeId: seoyeon },
    { title: '리허설 장소 알아보기', dueDate: '2026-11-13', assigneeId: null },
  ],
}

// ── 시연 시작 데이터 ─────────────────────────────────────────
// 서버 시드(backend/tools/seed.py)와 같은 사람·회의·할 일·제안·선호·시간표다. 목과 실서버가 같은 화면에서 시작한다.
// 서버 시드에 없는 것(조율, 확정 대기 회의, 알림, 에이전트가 한 일)은 넣지 않는다 — 시연 중에 생긴다.

const HELD = '2026-10-31T12:00:00+09:00' // 10/31 회의가 끝난 시각. 회의록·할 일 확정은 이 시각으로 찍혀 있다
const [MON, TUE, WED, THU, FRI] = [0, 1, 2, 3, 4]

/** 서버 시드의 지난 회의는 조율 없이 잡혔고 네 사람 모두 수락했다. 응답(누가 왔나)만 담는다 */
const allAccepted = (meetingId: Id, rationale: string): SeedProposal => ({
  meetingId,
  schedulingId: null,
  settled: false,
  rationale,
  gets: null,
  getsFrom: '아직 없음',
  absent: null,
  burdens: [],
  responses: { [jisu]: '수락', [minji]: '수락', [hyunwoo]: '수락', [seoyeon]: '수락' },
  feedback: {},
})

export const SEED: DemoState = {
  version: SEED_VERSION,
  clockNow: '2026-11-10T19:00:00+09:00', // 서버 시드의 "오늘" 11/10. 사용자 인터뷰 정리(11/8)가 늦음으로 보인다
  room: {
    id: ROOM_ID,
    name: '서비스디자인 팀 프로젝트',
    description: '학기 과제. 최종 발표와 시연까지 간다.',
    startDate: '2026-10-20',
    dueDate: '2026-12-11',
    inviteCode: 'T9K2QM',
    memberCount: 4,
    leaderId: jisu,
  },
  members: [
    { id: jisu, name: '지수', yieldTotal: 0, note: '팀장 · 자료조사' },
    { id: minji, name: '민지', yieldTotal: 0, note: '발표 · 수업이 많음' },
    { id: hyunwoo, name: '현우', yieldTotal: 3, note: '개발 · 평일 저녁 알바, 지난 두 회의에서 +2·+1' },
    { id: seoyeon, name: '서연', yieldTotal: 0, note: '디자인 · 비대면 선호' },
  ],
  tasks: [
    // 기한(11/8)이 오늘(11/10)보다 앞서고 끝나지 않았다 → 늦음
    task({ id: 't1', title: '사용자 인터뷰 정리', dueDate: '2026-11-08', assigneeId: jisu, status: '진행 중', meetingId: 'm2', confirmedBy: jisu, confirmedAt: HELD }),
    task({ id: 't2', title: '발표 슬라이드 초안', dueDate: '2026-11-13', assigneeId: minji, meetingId: 'm2', confirmedBy: jisu, confirmedAt: HELD }),
    task({ id: 't3', title: '프로토타입 화면 구현', dueDate: '2026-11-15', assigneeId: hyunwoo, status: '막힘', meetingId: 'm2', confirmedBy: jisu, confirmedAt: HELD }),
    // 10/27 회의에서 나와 10/31 회의에서 "끝났다"고 한 일 → 회의에서 끝난 일
    task({ id: 't4', title: '참고 사례 조사', dueDate: '2026-11-05', assigneeId: jisu, status: '완료', meetingId: 'm1', doneMeetingId: 'm2', confirmedBy: jisu, confirmedAt: HELD }),
    // 담당자 없음은 오류가 아니라 정상 시작 상태다
    task({ id: 't5', title: '발표 대본 작성', dueDate: '2026-11-17', assigneeId: null, meetingId: 'm2', confirmedBy: jisu, confirmedAt: HELD }),
    // 직접 추가한 할 일. 출처 회의가 없다
    task({ id: 't6', title: '대면 회의 장소 예약', dueDate: '2026-11-12', assigneeId: jisu, confirmedBy: jisu, confirmedAt: HELD }),
  ],
  suggestions: [
    { id: 's1', meetingId: 'm2', title: '디자인 시안 정리', dueDate: '2026-11-14', assigneeId: seoyeon },
    { id: 's2', meetingId: 'm2', title: '최종 발표 리허설 일정 잡기', dueDate: '2026-11-18', assigneeId: null },
    { id: 's3', meetingId: 'm2', title: '시연 영상 촬영 계획', dueDate: null, assigneeId: null },
  ],
  meetings: [
    {
      id: 'm1', topic: '역할 나누기', mode: '대면', status: 'done',
      startAt: '2026-10-27T16:00:00+09:00', endAt: '2026-10-27T18:00:00+09:00',
      transcript: [], minutes: null,
    },
    {
      id: 'm2', topic: '중간 발표 자료 나누기', mode: '비대면', status: 'done',
      startAt: '2026-10-31T10:00:00+09:00', endAt: '2026-10-31T12:00:00+09:00',
      transcript: [
        { speakerId: jisu, text: '오늘은 중간 발표 자료를 누가 어디까지 맡을지 정하죠.' },
        { speakerId: minji, text: '발표는 제가 할게요. 슬라이드 초안은 다음 주 목요일까지 가능해요.' },
        { speakerId: hyunwoo, text: '저는 프로토타입 화면을 구현할게요. 알바 때문에 평일 저녁은 어려워요.' },
        { speakerId: seoyeon, text: '디자인 시안은 제가 볼게요. 발표 대본은 아직 맡을 사람이 없어요.' },
        { speakerId: jisu, text: '사용자 인터뷰 정리는 제가 이번 주말까지 끝낼게요.' },
        { speakerId: null, text: '리허설 일정은 다음 회의에서 다시 이야기해요.' },
      ],
      minutes: {
        headline: '중간 발표 자료를 역할별로 나눔', status: 'done',
        decisions: ['발표는 민지, 프로토타입 구현은 현우가 맡는다.', '사용자 인터뷰 정리는 지수가 이번 주말까지 끝낸다.'],
        discussions: ['현우는 평일 저녁 알바가 있어 회의는 낮이 낫다.'],
        pendings: ['발표 대본을 누가 쓸지 정하지 못했다.', '최종 발표 리허설 일정.'],
      },
    },
  ],
  schedulings: [],
  proposals: [
    allAccepted('m1', '현우의 알바 시작 직전이지만, 네 사람이 다 비는 시간이 이 두 시간뿐이었습니다.'),
    allAccepted('m2', '금요일 오전은 민지의 수업이 끝난 뒤라 가장 덜 불편했습니다.'),
  ],
  notices: [],
  agentLog: [],
  // 최신순. 서버는 숫자 없이 조금/많이로만 내보낸다(notice/router.py _양보말)
  yieldRecords: [
    { id: 'y2', meetingLabel: '10월 31일 회의', userId: hyunwoo, why: '조금 불편한 시간을 맞춰 줬어요' },
    { id: 'y1', meetingLabel: '10월 27일 회의', userId: hyunwoo, why: '많이 불편한 시간을 맞춰 줬어요' },
  ],
  prefs: {
    [jisu]: { fromHour: 9, toHour: 22, mode: '상관없음', dayparts: ['오후'], avoid: '' },
    [minji]: { fromHour: 10, toHour: 21, mode: '대면', dayparts: ['오후', '저녁'], avoid: '오전은 수업이 많아서 힘들어요' },
    [hyunwoo]: { fromHour: 9, toHour: 18, mode: '상관없음', dayparts: ['오전', '오후'], avoid: '평일 저녁은 알바가 있어요' },
    [seoyeon]: { fromHour: 10, toHour: 23, mode: '비대면', dayparts: ['저녁', '밤'], avoid: '' },
  },
  scheduleItems: [
    item('s1', jisu, 101, '서비스디자인', 'class', 'everytime', TUE, hm(13), hm(14, 30)),
    item('s2', jisu, 102, '사용자조사', 'class', 'everytime', THU, hm(10, 30), hm(12)),
    item('s3', minji, 201, '인터랙션', 'class', 'everytime', MON, hm(10, 30), hm(12)),
    item('s4', minji, 202, '시각디자인', 'class', 'everytime', MON, hm(13), hm(14, 30)),
    item('s5', minji, 203, '디자인사', 'class', 'everytime', TUE, hm(9), hm(12)),
    item('s6', minji, 204, '타이포그래피', 'class', 'everytime', WED, hm(10, 30), hm(12)),
    item('s7', minji, 205, '프로젝트스튜디오', 'class', 'everytime', THU, hm(13), hm(16)),
    item('s8', minji, 206, '색채학', 'class', 'everytime', FRI, hm(9), hm(10, 30)),
    item('s9', hyunwoo, 301, '자료구조', 'class', 'everytime', WED, hm(9), hm(12)),
    // 현우의 알바: 묶음 하나(302)에 요일 다섯 줄. 서버 종류는 알바지만 시간표에는 "일정"으로 나간다
    ...[MON, TUE, WED, THU, FRI].map((d, i) => item(`s${10 + i}`, hyunwoo, 302, '편의점 알바', 'event', 'manual', d, hm(18), hm(22))),
    item('s15', seoyeon, 401, 'UX기초', 'class', 'everytime', WED, hm(13), hm(16)),
    item('s16', seoyeon, 402, '모션그래픽', 'class', 'everytime', FRI, hm(13), hm(14, 30)),
  ],
  nextSeq: 100,
}
