import type { Id, IsoDate, IsoDateTime, MeetingMode } from '../types/common.ts'
import type { Minutes, MeetingStatus } from '../types/meeting.ts'
import type { AgentLogEntry } from '../types/notification.ts'
import type { YieldLevel } from '../types/room.ts'
import type { ResponseState, SchedulingStatus } from '../types/scheduling.ts'
import type { TaskStatus } from '../types/task.ts'

// 시연 데이터. 디자인 브리프 "시안에 쓸 예시 데이터"와 시안10의 DATA를 그대로 옮겼다.
// 이 값은 서버의 DB 역할이라 보는 사람과 상관없는 원본만 담는다. 화면에 줄 모양(내 점수, can_*)은 mock/views.ts가 만든다.
// SEED는 직접 바꾸지 않는다. 저장소는 항상 structuredClone(SEED)로 시작한다(목업 버그 ④).

export const SEED_VERSION = 2

/** 사람 ID는 여기서 한 번만 정한다. 화면 코드에 'minji' 같은 값을 쓰지 않는다 */
export const USER = {
  jisu: 'u-jisu',
  minji: 'u-minji',
  hyunwoo: 'u-hyunwoo',
  seoyeon: 'u-seoyeon',
} as const

export const ROOM_ID: Id = 'room-1'

export type SeedMember = {
  id: Id
  name: string
  yieldLevel: YieldLevel
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
  doneAt: IsoDateTime | null // 완료로 바뀐 때. 완료 알림을 만든다
  dismissed: boolean // "삭제"한 할 일. 목록에서 빠진다
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
  meetingId: Id | null // 조율이 끝나 나온 회의
}

/** 수락·거절할 때 남긴 한 줄과, 에이전트가 그 말로 바꾼 선호 */
export type SeedFeedback = { text: string; change: string | null; undone: boolean }

/** 조율이 낸 회의의 사람별 부담과 응답 */
export type SeedProposal = {
  meetingId: Id
  settled: boolean
  rationale: string
  gets: Id | null // 이번에 양보 점수를 받는 사람
  getsFrom: YieldLevel // 그 사람의 조율 당시 누적 단계. 확정되면 한 단계 오른다
  yieldWhy: string // 확정되면 양보 기록에 남길 한 줄
  absent: Id | null // 불참안에서 빠진 사람
  burdens: { userId: Id; score: number; reason: string }[]
  responses: Record<Id, ResponseState>
  feedback: Record<Id, SeedFeedback>
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
  readNotices: Record<Id, Id[]> // 사람별로 읽은 알림 ID
  agentLog: AgentLogEntry[]
  yieldRecords: { id: Id; meetingLabel: string; userId: Id; why: string }[]
  nextSeq: number // 새로 만드는 항목의 ID 번호
}

const { jisu, minji, hyunwoo, seoyeon } = USER

const task = (t: Partial<SeedTask> & Pick<SeedTask, 'id' | 'title' | 'dueDate' | 'assigneeId'>): SeedTask => ({
  status: '시작 전',
  blockedReason: null,
  meetingId: null,
  confirmedBy: null,
  doneAt: null,
  dismissed: false,
  ...t,
})

/** 대본이 끝나면 나오는 회의안의 바탕. 회의 ID·응답은 조율이 끝날 때 붙는다 */
export type ScenarioResult = Omit<SeedProposal, 'meetingId' | 'settled' | 'responses' | 'feedback'>

/**
 * 시연 조율 대본: 팀장이 "조율 시작"을 누르면 목 서버가 이 대본을 그대로 다시 돌린다(실서버에서는 AI가 만든다).
 * 시드의 c1·m4는 이 대본을 한 번 돌린 결과다.
 */
export const DEMO_SCENARIO: { script: SeedUtterance[]; result: ScenarioResult } = {
  // 11/5 흐름: 팀원이 원하는 시간을 어필 → 판단 에이전트가 그중에서 고름 → 수락·거절. 2라운드부터는 판단이 먼저 말한다
  script: [
    { kind: 'appeal', round: 1, who: jisu, text: '저는 목요일 오후가 제일 좋아요. 그 시간에는 수업이 없어요.' },
    { kind: 'appeal', round: 1, who: hyunwoo, text: '저는 수요일 오후가 제일 좋아요. 평일 저녁은 알바가 있어 어려워요.' },
    { kind: 'appeal', round: 1, who: minji, text: '저는 수요일 오후가 좋아요. 오전에는 수업이 연달아 있어 어려워요.' },
    { kind: 'appeal', round: 1, who: seoyeon, text: '저는 저녁 비대면이 제일 좋아요. 이동이 없어서요.' },
    {
      kind: 'judge', round: 1, yieldChanges: [],
      text: '네 분이 원한 시간 중에서 골랐어요. 목요일 13:00–15:00, 대면을 제안합니다. 팀 전체로는 가장 덜 불편한 시간이에요.',
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
      text: '현우가 지난 두 번 많이 맞춰 줘서 이번엔 현우 쪽을 먼저 챙길게요. 대안으로 수요일 16:00–18:00, 비대면을 제안합니다. 대신 민지가 조금 맞춰 주게 됩니다.',
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
    yieldWhy: '수업 바로 뒤지만 현우를 먼저 챙기려고 맞춰 줬어요.',
    absent: null,
    burdens: [
      { userId: minji, score: 3, reason: '수업 바로 뒤예요' },
      { userId: jisu, score: 1, reason: '선호 시간대 안이에요' },
      { userId: hyunwoo, score: 1, reason: '알바 전까지 여유가 있어요' },
      { userId: seoyeon, score: 1, reason: '비대면이라 이동이 없어요' },
    ],
  },
}

export const SEED: DemoState = {
  version: SEED_VERSION,
  clockNow: '2026-11-10T19:00:00+09:00', // 11/10(화) 회의가 끝나고 회의록이 정리된 저녁
  room: {
    id: ROOM_ID,
    name: '서비스디자인 팀 프로젝트',
    description: '대학생 생활 속 불편을 하나 골라 서비스로 풀고, 화면 시안과 발표로 보여 주는 과제',
    startDate: '2026-10-13',
    dueDate: '2026-12-11',
    inviteCode: 'TEAM-4821',
    memberCount: 4,
    leaderId: jisu,
  },
  members: [
    { id: jisu, name: '지수', yieldLevel: '조금 맞춰 줌', note: '팀장' },
    { id: minji, name: '민지', yieldLevel: '아직 없음', note: '수업이 많음' },
    { id: hyunwoo, name: '현우', yieldLevel: '많이 맞춰 줌', note: '평일 저녁 알바, 지난 회의에서 두 번 맞춰 줌' },
    { id: seoyeon, name: '서연', yieldLevel: '아직 없음', note: '비대면 선호' },
  ],
  tasks: [
    task({ id: 't1', title: '경쟁 서비스 사례 조사', dueDate: '2026-11-07', assigneeId: jisu, status: '진행 중' }),
    task({ id: 't2', title: '경쟁 서비스 사례 조사 2차', dueDate: '2026-11-20', assigneeId: jisu }),
    task({ id: 't3', title: '중간 점검 자료', dueDate: '2026-11-15', assigneeId: null }),
    task({ id: 't4', title: '발표 대본 초안', dueDate: '2026-11-11', assigneeId: minji, meetingId: 'm2', confirmedBy: minji }),
    task({ id: 't5', title: '인터뷰 대상자 연락', dueDate: '2026-11-12', assigneeId: minji }),
    task({ id: 't6', title: '발표 슬라이드 틀 잡기', dueDate: '2026-11-14', assigneeId: minji, status: '진행 중' }),
    task({ id: 't7', title: '중간 점검 예상 질문 정리', dueDate: '2026-11-18', assigneeId: minji }),
    task({ id: 't8', title: '최종 발표 리허설 일정 잡기', dueDate: '2026-11-27', assigneeId: minji }),
    task({ id: 't9', title: '페르소나 정리', dueDate: '2026-11-05', assigneeId: minji, status: '완료' }),
    task({ id: 't10', title: '사용자 흐름 초안', dueDate: '2026-11-14', assigneeId: hyunwoo, meetingId: 'm2', confirmedBy: hyunwoo }),
    task({ id: 't11', title: '시연 시나리오 작성', dueDate: '2026-11-20', assigneeId: hyunwoo, meetingId: 'm2', confirmedBy: hyunwoo }),
    task({ id: 't12', title: '프로토타입 화면 연결', dueDate: '2026-11-20', assigneeId: hyunwoo, meetingId: 'm3', confirmedBy: hyunwoo }),
    task({ id: 't13', title: '프로토타입 기본 화면', dueDate: '2026-11-21', assigneeId: hyunwoo, status: '진행 중' }),
    task({
      id: 't14', title: '인터뷰 결과 정리', dueDate: '2026-11-13', assigneeId: seoyeon,
      status: '막힘', blockedReason: '인터뷰 녹취 2건이 아직 안 왔어요',
    }),
    // 회의에서 끝났다고 말해 완료로 바뀐 일 → 완료 알림
    task({ id: 't15', title: '화면 시안 3종', dueDate: '2026-11-19', assigneeId: seoyeon, status: '완료', doneAt: '2026-11-10T18:42:00+09:00' }),
  ],
  suggestions: [
    { id: 's1', meetingId: 'm3', title: '중간 점검 발표 구성안', dueDate: '2026-11-13', assigneeId: minji },
    { id: 's2', meetingId: 'm3', title: '인터뷰 질문지 보완', dueDate: '2026-11-13', assigneeId: null },
    { id: 's3', meetingId: 'm3', title: '사용성 테스트 참가자 모집', dueDate: '2026-11-13', assigneeId: null },
  ],
  meetings: [
    {
      id: 'm1', topic: '주제 정하고 역할 나누기', mode: '대면', status: 'done',
      startAt: '2026-10-28T16:00:00+09:00', endAt: '2026-10-28T17:00:00+09:00',
      transcript: [
        { speakerId: jisu, text: '주제는 대학생 팀플 도우미로 가요.' },
        { speakerId: jisu, text: '역할은 자료조사 저, 발표 민지, 개발 현우, 디자인 서연이요.' },
      ],
      minutes: { headline: '주제 정하고 역할 나누기', status: 'done', decisions: ['주제: 대학생 팀플 도우미', '역할 나누기'], discussions: [], pendings: [] },
    },
    {
      id: 'm2', topic: '발표 흐름과 화면 정하기', mode: '대면', status: 'done',
      startAt: '2026-11-04T16:00:00+09:00', endAt: '2026-11-04T16:55:00+09:00',
      transcript: [
        { speakerId: hyunwoo, text: '사용자 흐름은 제가 먼저 그려 볼게요. 다음 주 토요일까지요.' },
        { speakerId: minji, text: '발표 대본 초안은 제가 맡을게요.' },
        { speakerId: seoyeon, text: '시연 시나리오도 누군가 써야 해요.' },
        { speakerId: hyunwoo, text: '시연은 화면 만드는 제가 쓰는 게 낫겠어요.' },
      ],
      minutes: {
        headline: '발표 흐름과 화면 정하기', status: 'done',
        decisions: ['사용자 흐름 초안은 현우', '발표 대본 초안은 민지', '시연 시나리오는 현우'], discussions: [], pendings: [],
      },
    },
    {
      id: 'm3', topic: '중간 점검 자료 나누기', mode: '대면', status: 'done',
      startAt: '2026-11-10T16:00:00+09:00', endAt: '2026-11-10T16:40:00+09:00',
      transcript: [
        { speakerId: jisu, text: '16일 중간 점검 전에 자료를 어떻게 나눌지 정해요.' },
        { speakerId: seoyeon, text: '화면 시안 세 개는 어제 다 끝냈어요. 폴더에 올려 뒀어요.' },
        { speakerId: minji, text: '발표 구성안은 제가 금요일까지 만들어 올게요.' },
        { speakerId: jisu, text: '중간 점검 자료 취합은 제가 맡을게요.' },
        { speakerId: seoyeon, text: '인터뷰 질문지는 조금 더 다듬어야 할 것 같아요.' },
        { speakerId: hyunwoo, text: '질문지는 누가 할지 다음에 정해요.' },
        { speakerId: hyunwoo, text: '프로토타입 화면 연결은 제가 할게요. 다음 주 금요일까지요.' },
        { speakerId: minji, text: '사용성 테스트 참가자도 주말 전까지 모아야 해요.' },
        { speakerId: jisu, text: '경쟁 서비스 2차 조사는 안 해도 될 것 같아요. 1차로 충분해요.' },
        { speakerId: seoyeon, text: '발표 순서는 구성안 보고 다시 얘기해요.' },
      ],
      minutes: {
        headline: '중간 점검 자료 나누기', status: 'done',
        decisions: ['발표 구성안은 민지가 금요일까지', '중간 점검 자료 취합은 지수', '프로토타입 화면 연결은 현우', '경쟁 서비스 2차 조사는 하지 않음'],
        discussions: ['인터뷰 질문지를 더 다듬기', '사용성 테스트 참가자 미리 모으기'],
        pendings: ['발표 순서: 구성안 보고 다시', '질문지 담당자: 다음 회의에서'],
      },
    },
    // 조율이 낸 다음 회의. 지수·현우는 수락, 민지·서연은 아직 대기
    {
      id: 'm4', topic: '중간 점검 전 회의', mode: '비대면', status: 'proposed',
      startAt: '2026-11-18T16:00:00+09:00', endAt: '2026-11-18T18:00:00+09:00',
      transcript: [], minutes: null,
    },
  ],
  schedulings: [
    {
      id: 'c1', topic: '중간 점검 전 회의', durationMin: 120, mode: '상관없음', status: 'agreed', meetingId: 'm4',
      windowStart: '2026-11-16T00:00:00+09:00', windowEnd: '2026-11-20T23:59:00+09:00',
      script: DEMO_SCENARIO.script,
    },
  ],
  proposals: [
    {
      ...DEMO_SCENARIO.result,
      meetingId: 'm4', settled: false,
      responses: { [jisu]: '수락', [minji]: '대기', [hyunwoo]: '수락', [seoyeon]: '대기' },
      feedback: {},
    },
  ],
  readNotices: {},
  agentLog: [
    { id: 'a1', at: '2026-11-10T18:42:00+09:00', what: "11/10 회의록에서 '화면 시안 3종'을 완료로 바꿨어요", why: '서연이 회의에서 다 끝냈다고 말했어요.' },
    { id: 'a2', at: '2026-11-10T18:42:00+09:00', what: '11/10 회의록에서 할 일 제안 4개를 만들었어요', why: '확정 전까지는 회의록에만 보여요.' },
    { id: 'a3', at: '2026-11-10T09:12:00+09:00', what: '조율 결과를 냈어요', why: '현우가 지난 두 번 많이 맞춰 줘서 이번엔 현우 쪽을 먼저 챙겼어요.' },
  ],
  yieldRecords: [
    { id: 'y1', meetingLabel: '11월 4일 회의', userId: hyunwoo, why: '알바 시작을 한 시간 늦춰 대면 회의에 맞춰 줬어요.' },
    { id: 'y2', meetingLabel: '10월 28일 회의', userId: hyunwoo, why: '수업 끝나자마자 이동해 회의에 왔어요. 지수도 조금 맞춰 줬어요.' },
  ],
  nextSeq: 100,
}
