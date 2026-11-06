import { mockContext } from '../mock/context.ts'
import { dispatch } from '../mock/store.ts'
import { buildMyTasks, buildTeamTasks } from '../mock/views.ts'
import type { Id } from '../types/common.ts'
import type { Task, TaskInput, TaskStatus, TeamTasks } from '../types/task.ts'
import { request, withMock, withMockWrite } from './client.ts'
import { toServerState, toTask, toTeamTasks, type ServerTask, type ServerTaskList } from './convert.ts'

// 할 일. 팀 할 일·내 할 일·홈이 같은 Task 모양을 쓴다.

const toServerInput = (input: Partial<TaskInput>) => ({
  title: input.title,
  assignee_user_id: input.assigneeId === undefined ? undefined : input.assigneeId && Number(input.assigneeId),
  due_date: input.dueDate,
})

/** 팀 할 일: 확정된 것만, 사람별 남은 개수와 회의록에 남은 제안 수 */
export function getTeamTasks(roomId: Id): Promise<TeamTasks> {
  return withMock(
    async () => toTeamTasks(await request<ServerTaskList>(`/rooms/${roomId}/tasks`)),
    () => {
      const { s, viewer, now } = mockContext()
      return buildTeamTasks(s, viewer, now)
    },
  )
}

/** 내 할 일: 기한 순 */
export function getMyTasks(roomId: Id): Promise<Task[]> {
  return withMock(
    async () => (await request<{ tasks: ServerTask[] }>(`/rooms/${roomId}/tasks/mine`)).tasks.map(toTask),
    () => {
      const { s, viewer, now } = mockContext()
      return buildMyTasks(s, viewer, now)
    },
  )
}

/** 상태 바꾸기 (담당자만). 막힘이면 이유 한 줄이 막힘 알림에 붙는다 */
export function changeTaskStatus(roomId: Id, taskId: Id, status: TaskStatus, reason: string | null = null) {
  return withMockWrite(
    () =>
      request<void>(`/rooms/${roomId}/tasks/${taskId}/status`, {
        method: 'PATCH',
        body: { state: toServerState(status), reason },
      }),
    () => dispatch({ type: 'task/status', taskId, status, reason }),
  )
}

/** 제목·담당자·기한 고치기 (전원) */
export function editTask(roomId: Id, taskId: Id, patch: Partial<TaskInput>) {
  return withMockWrite(
    () => request<void>(`/rooms/${roomId}/tasks/${taskId}`, { method: 'PATCH', body: toServerInput(patch) }),
    () => dispatch({ type: 'task/edit', taskId, patch }),
  )
}

/** 직접 추가: 출처는 "직접 추가" */
export function addTask(roomId: Id, input: TaskInput) {
  return withMockWrite(
    () => request<void>(`/rooms/${roomId}/tasks`, { method: 'POST', body: toServerInput(input) }),
    () => dispatch({ type: 'task/add', input }),
  )
}

/** 할 일 삭제 (전원). 서버 경로 이름은 dismiss지만 화면 문구는 "삭제" */
export function dismissTask(roomId: Id, taskId: Id) {
  return withMockWrite(
    () => request<void>(`/rooms/${roomId}/tasks/${taskId}/dismiss`, { method: 'POST' }),
    () => dispatch({ type: 'task/dismiss', taskId }),
  )
}
