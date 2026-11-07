import type { Id, IsoDate, IsoDateTime, MeetingMode } from './common.ts'
import type { SchedulingStatus } from './scheduling.ts'
import type { Task } from './task.ts'

/** 회의 상태. 조율이 끝나면 바로 confirmed가 되고, proposed는 서버가 정리 중일 때만 잠깐 보인다 */
export type MeetingStatus = 'proposed' | 'confirmed' | 'done' | 'cancelled'

/** 일정 목록과 홈 다음 회의의 한 줄 */
export type MeetingBrief = {
  id: Id
  topic: string
  startAt: IsoDateTime
  endAt: IsoDateTime
  mode: MeetingMode
  status: MeetingStatus
  settled: boolean
  suggestionCount: number // 지난 회의: 확정 전 할 일 제안 수 ("제안 N개")
}

/** 조율 중인 회의: 언제 잡힐지 몰라도 목록에 자리를 잡아 둔다 */
export type CoordinatingBrief = {
  id: Id
  topic: string
  windowStart: IsoDateTime
  windowEnd: IsoDateTime
  status: SchedulingStatus
}

/** 일정 탭: 조율 중 → 잡힌 회의 → 지난 회의 */
export type Schedule = {
  coordinating: CoordinatingBrief[]
  upcoming: MeetingBrief[]
  past: MeetingBrief[]
}

export type TranscriptLine = {
  seq: number
  speakerId: Id | null
  speakerName: string | null // 받아적는 동안은 "목소리 A"
  text: string
}

export type MinutesStatus = 'summarizing' | 'done' | 'failed'

/** 회의록 요약: 결정 / 논의 / 보류 */
export type Minutes = {
  headline: string
  status: MinutesStatus
  decisions: string[]
  discussions: string[]
  pendings: string[]
}

/** 확정 전 AI 할 일 제안. 할 일 탭에는 보이지 않는다 */
export type Suggestion = {
  id: Id
  title: string
  dueDate: IsoDate | null
  assigneeId: Id | null
  assigneeName: string | null
}

export type MeetingDetail = {
  id: Id
  topic: string
  startAt: IsoDateTime
  endAt: IsoDateTime
  mode: MeetingMode
  status: MeetingStatus
  attendees: string[]
  transcript: TranscriptLine[] // 원문. 요약이 실패해도 그대로 보인다
  minutes: Minutes | null // 요약 전이면 null
  tasks: Task[] // 이 회의에서 확정된 할 일
  suggestions: Suggestion[]
}

/** 회의록 목록의 한 줄 */
export type MeetingSummary = {
  id: Id
  topic: string
  headline: string | null
  startAt: IsoDateTime
  mode: MeetingMode
  status: MeetingStatus
  attendees: string[]
  hasTranscript: boolean
  suggestionCount: number
}

export type RecordInput = {
  meetingId: Id | null // 확정된 회의 없이도 기록할 수 있다
  topic: string | null
  mode: MeetingMode
}

export type SuggestionPatch = {
  title?: string
  assigneeId?: Id | null
  dueDate?: IsoDate | null
}
