import type { Id } from '../types/common.ts'
import type { TaskInput, TaskStatus, TeamTasks } from '../types/task.ts'
import { request, write } from './client.ts'
import { toServerState, toTeamTasks, type ServerTaskList } from './convert.ts'

// 할 일. 팀 할 일·홈이 같은 Task 모양을 쓴다.

const toServerInput = (input: Partial<TaskInput>) => ({
  title: input.title,
  assignee_user_id: input.assigneeId === undefined ? undefined : input.assigneeId && Number(input.assigneeId),
  due_date: input.dueDate,
})

/** 팀 할 일: 확정된 것만, 사람별 남은 개수와 회의록에 남은 제안 수 */
export async function getTeamTasks(roomId: Id): Promise<TeamTasks> {
  return toTeamTasks(await request<ServerTaskList>(`/rooms/${roomId}/tasks`))
}

/** 상태 바꾸기 (담당자만). 막힘이면 이유 한 줄이 막힘 알림에 붙는다 */
export function changeTaskStatus(roomId: Id, taskId: Id, status: TaskStatus, reason: string | null = null) {
  return write(() =>
    request<void>(`/rooms/${roomId}/tasks/${taskId}/status`, {
      method: 'PATCH',
      body: { state: toServerState(status), reason },
    }),
  )
}

/** 제목·담당자·기한 고치기 (전원) */
export function editTask(roomId: Id, taskId: Id, patch: Partial<TaskInput>) {
  return write(() => request<void>(`/rooms/${roomId}/tasks/${taskId}`, { method: 'PATCH', body: toServerInput(patch) }))
}

/**
 * 직접 추가: 제안을 거치지 않고 바로 확정된 할 일이 된다.
 * 회의록에서 추가하면 그 회의가 출처, 할 일 탭에서 추가하면(meetingId 없음) 출처는 "직접 추가"
 */
export function addTask(roomId: Id, input: TaskInput, meetingId: Id | null = null) {
  return write(() =>
    request<void>(`/rooms/${roomId}/tasks`, {
      method: 'POST',
      body: { ...toServerInput(input), meeting_id: meetingId && Number(meetingId) },
    }),
  )
}

/** 할 일 삭제 (전원). 서버 경로 이름은 dismiss지만 화면 문구는 "삭제" */
export function dismissTask(roomId: Id, taskId: Id) {
  return write(() => request<void>(`/rooms/${roomId}/tasks/${taskId}/dismiss`, { method: 'POST' }))
}
