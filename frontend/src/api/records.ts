import { mockContext } from '../mock/context.ts'
import { dispatch } from '../mock/store.ts'
import { buildMeetingDetail, buildMeetingList } from '../mock/views.ts'
import type { Id } from '../types/common.ts'
import type { MeetingDetail, MeetingSummary, SuggestionPatch } from '../types/meeting.ts'
import { request, withMock, withMockWrite } from './client.ts'
import {
  toMeetingDetail,
  toMeetingSummary,
  type ServerMeetingDetail,
  type ServerMeetingSummary,
} from './convert.ts'

// 회의 기록·회의록·할 일 제안. 장면 2의 앞부분(회의에서 할 일로)이 여기서 나온다.

export function getMeetings(roomId: Id): Promise<MeetingSummary[]> {
  return withMock(
    async () => {
      const r = await request<{ meetings: ServerMeetingSummary[] }>(`/rooms/${roomId}/meetings`)
      return r.meetings.map(toMeetingSummary)
    },
    () => buildMeetingList(mockContext().s),
  )
}

/** 회의록: 원문 + 요약 + 그 회의에서 확정된 할 일 + 확정 전 제안 */
export function getMeeting(roomId: Id, meetingId: Id): Promise<MeetingDetail> {
  return withMock(
    async () => toMeetingDetail(await request<ServerMeetingDetail>(`/rooms/${roomId}/meetings/${meetingId}`)),
    () => {
      const { s, viewer, now } = mockContext()
      return buildMeetingDetail(s, meetingId, viewer, now)
    },
  )
}

/** 직접 쓰기: AI 없이 도는 길 */
export function writeTranscript(roomId: Id, meetingId: Id, text: string): Promise<void> {
  return withMockWrite(
    () => request<void>(`/rooms/${roomId}/meetings/${meetingId}/transcript`, { method: 'PUT', body: { text } }),
    () => dispatch({ type: 'meeting/transcript', meetingId, text }),
  )
}

/** 할 일 제안 한꺼번에 확정. 담당자가 없어도 확정된다 */
export function confirmSuggestions(roomId: Id, suggestionIds: Id[]): Promise<void> {
  return withMockWrite(
    () =>
      request<void>(`/rooms/${roomId}/suggestions/confirm`, {
        method: 'POST',
        body: { suggestion_ids: suggestionIds.map(Number) },
      }),
    () => dispatch({ type: 'suggestion/confirm', suggestionIds, by: mockContext().viewer }),
  )
}

export function editSuggestion(roomId: Id, suggestionId: Id, patch: SuggestionPatch): Promise<void> {
  const body = {
    title: patch.title,
    assignee_user_id: patch.assigneeId === undefined ? undefined : patch.assigneeId && Number(patch.assigneeId),
    due_date: patch.dueDate,
  }
  return withMockWrite(
    () => request<void>(`/rooms/${roomId}/suggestions/${suggestionId}`, { method: 'PATCH', body }),
    () => dispatch({ type: 'suggestion/edit', suggestionId, patch }),
  )
}

/** 제안 삭제. 되돌릴 수 없어 화면에서 한 번 더 묻는다 */
export function dismissSuggestion(roomId: Id, suggestionId: Id): Promise<void> {
  return withMockWrite(
    () => request<void>(`/rooms/${roomId}/suggestions/${suggestionId}`, { method: 'DELETE' }),
    () => dispatch({ type: 'suggestion/dismiss', suggestionId }),
  )
}
