import type { IsoDate } from './common.ts'
import type { CoordinatingBrief, MeetingBrief } from './meeting.ts'
import type { Task } from './task.ts'

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
  inviteCode: string // 방 막 만든 직후에 보인다
  joinedCount: number
  memberCount: number
}
