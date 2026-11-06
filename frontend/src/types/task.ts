import type { Id, IsoDate, IsoDateTime } from './common.ts'

export const TASK_STATUSES = ['시작 전', '진행 중', '막힘', '완료'] as const
export type TaskStatus = (typeof TASK_STATUSES)[number]

/** 어느 회의에서 나왔는지. null이면 "직접 추가" */
export type TaskSource = {
  meetingId: Id
  heldOn: IsoDate
  topic: string
} | null

export type Task = {
  id: Id
  title: string
  dueDate: IsoDate | null
  assigneeId: Id | null // null = 담당자 없음 (오류가 아니라 정상인 시작 상태)
  assigneeName: string | null
  status: TaskStatus
  blockedReason: string | null // 막힘을 고를 때 받은 한 줄. 막힘 알림에 붙는다
  source: TaskSource
  confirmedByName: string | null
  confirmedAt: IsoDateTime | null
  isLate: boolean // 기한이 지났는데 완료가 아님 (시연 시계 기준)
  canChangeStatus: boolean // 담당자만 true
  canEdit: boolean
}

export type TaskCount = {
  userId: Id
  name: string
  remaining: number
}

export type TeamTasks = {
  tasks: Task[] // 확정된 것만
  counts: TaskCount[] // 사람별 남은 할 일 수
  suggestionCount: number // 회의록에 남은 확정 전 제안 수
}

export type TaskInput = {
  title: string
  assigneeId: Id | null
  dueDate: IsoDate | null
}
