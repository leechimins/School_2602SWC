import type { Id, IsoDate, IsoDateTime, MeetingMode } from './common.ts'
import type { YieldLevel } from './room.ts'

/** 남의 불편 정도. 1점 = 괜찮음, 2~3점 = 조금, 4~5점 = 많이. 내 것만 숫자(myScore)로 따로 받는다 */
export type Burden = '괜찮음' | '조금' | '많이'

/** 회의안 응답 */
export type ResponseState = '대기' | '수락' | '거절'

/**
 * 조율 상태. 화면 문구가 아니라 화면 갈래를 나누는 값이라 서버 코드를 그대로 쓴다.
 * running 라운드 도는 중 · agreed 전원 합의(사람이 수락·거절) · settled 판단 에이전트가 정함(바로 확정) · failed 후보 없음
 */
export type SchedulingStatus = 'running' | 'agreed' | 'settled' | 'failed'

export type SchedulingInput = {
  topic: string
  windowStart: IsoDate
  windowEnd: IsoDate
  durationMin: number // 30분 단위
  mode: MeetingMode | '상관없음'
}

export type Slot = {
  startAt: IsoDateTime
  endAt: IsoDateTime
  mode: MeetingMode
}

/** 판단 에이전트가 바꾼 누적 양보 단계: 누가, 전 단계 → 뒤 단계 */
export type YieldChange = {
  userId: Id
  name: string
  from: YieldLevel
  to: YieldLevel
}

/**
 * 시간 정하는 과정의 발언 한 줄.
 * appeal = 팀원이 원하는 시간 어필, answer = 판단 에이전트 안에 대한 수락·거절, judge = 판단 에이전트
 */
export type Utterance = {
  seq: number
  round: number // 1~3
  kind: 'appeal' | 'answer' | 'judge'
  speakerId: Id | null // 판단 에이전트는 null
  speakerName: string | null
  text: string
  answer: '수락' | '거절' | null
  burden: Burden | null // 남의 불편은 단계로만
  myScore: number | null // 내 발언일 때만 숫자
  slot: Slot | null // 판단 에이전트가 낸 시간
  yieldChanges: YieldChange[]
}

export type Scheduling = {
  id: Id
  topic: string
  windowStart: IsoDateTime
  windowEnd: IsoDateTime
  durationMin: number
  mode: MeetingMode | '상관없음'
  status: SchedulingStatus
  roundsUsed: number
  utterances: Utterance[] // 한 번에 받아 프론트에서 하나씩 보여 준다
  proposalId: Id | null // 조율이 끝나 나온 회의
}

/** 회의 일정 조율 확인의 사람별 부담 줄 */
export type Responder = {
  userId: Id
  name: string
  state: ResponseState
  burden: Burden
  reason: string
  yieldLevel: YieldLevel
  feedback: string | null
}

/** 이번에 양보 점수를 받는 사람: 누적 단계가 어떻게 바뀌는지. 숫자는 본인에게만(Proposal.myYieldPoints) */
export type YieldGetter = {
  userId: Id
  name: string
  isMe: boolean
  burden: Burden // 맞춰 준 시간이 얼마나 불편했는지
  from: YieldLevel
  to: YieldLevel // 회의가 확정되면 이 단계가 된다. 가장 높은 단계면 from과 같다
}

/** 수락·거절할 때 내가 남긴 한 줄과, 내 에이전트가 그 말로 바꾼 선호 */
export type MyFeedback = {
  text: string
  change: string | null // "다음부터 수업 바로 뒤는 30분 띄워서 잡을게요". 시간과 상관없는 말이면 null
  undone: boolean // 되돌리기를 눌렀다
}

/** 회의 일정 조율 확인. 보는 사람마다 my* 값이 다르다 */
export type Proposal = {
  id: Id
  schedulingId: Id | null // "조율 과정 보기"로 돌아갈 조율
  roundsUsed: number | null // 몇 라운드에서 정해졌는지
  topic: string
  startAt: IsoDateTime
  endAt: IsoDateTime
  mode: MeetingMode
  confirmed: boolean // 전원 수락 또는 조정으로 확정됨
  settled: boolean // 판단 에이전트가 정해 바로 확정 (화면 "확정 · 조정")
  rationale: string // 누구를 왜 배려했는지 한 줄
  myScore: number | null // 내 불편 1~5. 빠진 사람이면 null
  myReason: string
  myYieldPoints: number // 이번에 내가 받을 양보 점수
  myState: ResponseState | null // 응답 대상이 아니면 null
  canRespond: boolean
  feedbackOnly: boolean // 조정안은 수락·거절 없이 피드백 한 줄만
  responders: Responder[]
  absentName: string | null // 불참안에서 빠진 사람
  yieldGetter: YieldGetter | null
  myFeedback: MyFeedback | null
}

export type RespondInput = {
  accept: boolean
  feedback: string | null
}
