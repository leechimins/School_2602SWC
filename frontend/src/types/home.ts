import type { IsoDate } from './common.ts'
import type { CoordinatingBrief, MeetingBrief } from './meeting.ts'
import type { Task } from './task.ts'

/** 에이전트가 먼저 꺼내는 "회의 잡을까요?" — 회의가 필요한 이유가 생겼을 때 팀장에게만 */
export type MeetingSuggestion = {
  kind: 'blocked' | 'late' | 'deadline' | 'gap'
  reason: string // 왜 지금인지 한 줄
  topic: string // 조율 화면에 미리 채울 주제
  windowStart: IsoDate
  windowEnd: IsoDate
}

export type Home = {
  roomName: string
  today: IsoDate // 시연 시계 기준
  startDate: IsoDate
  dueDate: IsoDate
  dDay: number
  nextMeeting: MeetingBrief | null
  coordinating: CoordinatingBrief | null // 다음 회의 대신 "조율 중"
  myTasks: Task[] // 기한 순
  unreadCount: number
  canStartScheduling: boolean // 회의 잡기 버튼은 팀장에게만
  suggestion: MeetingSuggestion | null
  inviteCode: string // 방 막 만든 직후에 보인다
  joinedCount: number
  memberCount: number
}
