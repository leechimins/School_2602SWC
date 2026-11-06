import type { Id, IsoDateTime } from './common.ts'

/**
 * 알림 종류. 앞의 셋(늦음·막힘·완료)이 할 일 알림 카드 3종이고 이 순서가 정렬 순서다.
 * 늦음·막힘은 챙기라는 알림, 완료만 좋은 소식이라 뱃지 색이 다르다.
 */
export const NOTICE_KINDS = ['늦음', '막힘', '완료', '회의 30분 전', '회의 제안', '회의 확정'] as const
export type NoticeKind = (typeof NOTICE_KINDS)[number]

export type Notice = {
  id: Id
  kind: NoticeKind
  reason: string // 이유 한 줄 (에이전트가 한 일은 항상 "왜"와 함께)
  taskId: Id | null
  taskTitle: string | null
  meetingId: Id | null
  createdAt: IsoDateTime
  read: boolean
}

export type NoticeList = {
  notices: Notice[] // 종류 순서 → 최신 순
  unreadCount: number
}

/** 에이전트가 한 일: 무엇을, 왜 */
export type AgentLogEntry = {
  id: Id
  at: IsoDateTime
  what: string
  why: string
}

/** 양보 기록: 회의마다 누가 왜 맞춰 줬는지 */
export type YieldRecord = {
  id: Id
  meetingLabel: string // "11월 4일 회의"
  userId: Id
  name: string
  why: string
}

export type ActivityLog = {
  agentLog: AgentLogEntry[]
  yieldRecords: YieldRecord[]
}
