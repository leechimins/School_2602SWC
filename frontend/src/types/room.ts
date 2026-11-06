import type { Id, IsoDate } from './common.ts'

/** 누적 양보 단계. 남의 누적 점수는 숫자 없이 이 단계로만 보인다 */
export const YIELD_LEVELS = ['아직 없음', '조금 맞춰 줌', '많이 맞춰 줌'] as const
export type YieldLevel = (typeof YIELD_LEVELS)[number]

export type Member = {
  id: Id
  name: string
  isLeader: boolean // 팀장 뱃지만 붙는다. 역할은 보여 주지 않는다
  isMe: boolean
  yieldLevel: YieldLevel
}

export type Room = {
  id: Id
  name: string
  description: string
  startDate: IsoDate
  dueDate: IsoDate
  inviteCode: string
  memberCount: number // 정원
  joinedCount: number
  leaderId: Id
  members: Member[] // 팀장이 맨 위
  canStartScheduling: boolean // 권한은 서버가 판단한다
}

export type RoomInput = {
  name: string
  description: string
  startDate: IsoDate
  dueDate: IsoDate
  memberCount: number
}
