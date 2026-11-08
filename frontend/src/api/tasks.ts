import { emitLate } from '../mock/actions.ts'
import { mockContext } from '../mock/context.ts'
import { dispatch } from '../mock/store.ts'
import { buildTeamTasks } from '../mock/views.ts'
import type { Id } from '../types/common.ts'
import type { TaskInput, TaskStatus, TeamTasks } from '../types/task.ts'
import { ApiError, request, withMock, withMockWrite } from './client.ts'
import { toServerState, toTeamTasks, type ServerTaskList } from './convert.ts'

// 할 일. 팀 할 일·홈이 같은 Task 모양을 쓴다.

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
      // 서버처럼 목록을 부를 때 늦음 알림을 낸다. 새로 생긴 게 있을 때만 바꿔 다시 불러오기가 돌지 않게 한다
      if (emitLate(mockContext().s) !== mockContext().s) dispatch({ type: 'notice/late' })
      const { s, viewer, now } = mockContext()
      return buildTeamTasks(s, viewer, now)
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
    () => {
      const { s, viewer } = mockContext()
      const task = s.tasks.find((t) => t.id === taskId)
      if (task && task.assigneeId !== null && task.assigneeId !== viewer) {
        throw new ApiError(403, 'NOT_ASSIGNEE', '담당자만 상태를 바꿀 수 있습니다.')
      }
      dispatch({ type: 'task/status', taskId, status, reason, by: viewer })
    },
  )
}

/** 제목·담당자·기한 고치기 (전원) */
export function editTask(roomId: Id, taskId: Id, patch: Partial<TaskInput>) {
  return withMockWrite(
    () => request<void>(`/rooms/${roomId}/tasks/${taskId}`, { method: 'PATCH', body: toServerInput(patch) }),
    () => dispatch({ type: 'task/edit', taskId, patch }),
  )
}

/**
 * 직접 추가: 제안을 거치지 않고 바로 확정된 할 일이 된다.
 * 회의록에서 추가하면 그 회의가 출처, 할 일 탭에서 추가하면(meetingId 없음) 출처는 "직접 추가"
 */
export function addTask(roomId: Id, input: TaskInput, meetingId: Id | null = null) {
  return withMockWrite(
    () =>
      request<void>(`/rooms/${roomId}/tasks`, {
        method: 'POST',
        body: { ...toServerInput(input), meeting_id: meetingId && Number(meetingId) },
      }),
    () => dispatch({ type: 'task/add', input, meetingId, by: mockContext().viewer }),
  )
}

/** 할 일 삭제 (전원). 서버 경로 이름은 dismiss지만 화면 문구는 "삭제" */
/** "필요 없어 보이는 일"을 그대로 두기. 서버에 이 목록이 없어 목 데이터에만 남긴다 */
export function keepTask(taskId: Id): Promise<void> {
  dispatch({ type: 'task/keep', taskId })
  return Promise.resolve()
}

export function dismissTask(roomId: Id, taskId: Id) {
  return withMockWrite(
    () => request<void>(`/rooms/${roomId}/tasks/${taskId}/dismiss`, { method: 'POST' }),
    () => dispatch({ type: 'task/dismiss', taskId }),
  )
}
