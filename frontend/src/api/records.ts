import { mockContext } from '../mock/context.ts'
import { DEMO_RECORDING } from '../mock/seed.ts'
import { dispatch, getState } from '../mock/store.ts'
import { buildMeetingDetail, buildMeetingList } from '../mock/views.ts'
import type { Id } from '../types/common.ts'
import type { MeetingDetail, MeetingSummary, RecordInput, SuggestionPatch } from '../types/meeting.ts'
import { USE_MOCK, isRealServer, request, withMock, withMockWrite } from './client.ts'
import {
  toServerMode,
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

/** 회의 기록 시작: 잡힌 회의가 없어도 주제 한 줄로 바로 연다. 새 회의 ID를 돌려준다 */
export function createMeeting(roomId: Id, input: RecordInput): Promise<Id> {
  return withMockWrite(
    async () => {
      const r = await request<{ id: number }>(`/rooms/${roomId}/meetings`, {
        method: 'POST',
        body: { meeting_id: input.meetingId && Number(input.meetingId), topic: input.topic, mode: toServerMode(input.mode) },
      })
      return String(r.id)
    },
    () => {
      const meetingId = `m${getState().nextSeq}`
      dispatch({ type: 'meeting/create', meetingId, input })
      return meetingId
    },
  )
}

/**
 * 받아적기를 쓸 수 있는지. 실제 음성 인식(백엔드 #40)과 말한 사람 정하기(#41)가 붙기 전까지 받아적기는 시연 대본이라
 * 목 모드에서만 연다. 실서버에서는 대본이 진짜 회의 원문으로 저장되지 않게 직접 쓰기만 쓴다.
 */
export function canRecordLive(): boolean {
  return !isRealServer()
}

/**
 * 받아적기에 쌓일 말(목 모드 시연 대본). 한 줄씩 흘린다.
 * speakerId는 "목소리 A"를 누구로 짐작해 둘지에만 쓰고, 정하는 것은 받아적는 사람이다.
 */
export function liveTranscript(): { speakerId: Id; text: string }[] {
  if (!canRecordLive()) return []
  return DEMO_RECORDING.lines.map((l) => ({ speakerId: l.who, text: l.text }))
}

/**
 * 원문 저장: 직접 쓰기와 받아적기가 같은 길로 저장한다. 한 줄에 한 말, "이름: 말"이면 말한 사람으로 읽는다.
 * 원문을 먼저 저장하고 정리(summarize)는 따로 부른다 — 정리가 실패해도 원문은 남는다.
 */
export function writeTranscript(roomId: Id, meetingId: Id, text: string): Promise<void> {
  return withMockWrite(
    () => request<void>(`/rooms/${roomId}/meetings/${meetingId}/transcript`, { method: 'PUT', body: { text } }),
    () => dispatch({ type: 'meeting/transcript', meetingId, text }),
  )
}

const SUMMARIZE_TIMEOUT_MS = 25_000 // 정리는 20초까지 걸린다(브리프 "기다림과 빈 화면")
const MOCK_SUMMARIZE_MS = 1_800 // 목 모드에서도 정리 중 화면이 잠깐 보이게

/** 회의록 정리 + 할 일 뽑기(AI). 실패하면 "잠시 후 다시 해 주세요." 한 줄과 다시 하기로 이어 간다 */
export async function summarizeMeeting(roomId: Id, meetingId: Id): Promise<void> {
  if (USE_MOCK) await new Promise((resolve) => setTimeout(resolve, MOCK_SUMMARIZE_MS))
  return withMockWrite(
    () =>
      request<void>(`/rooms/${roomId}/meetings/${meetingId}/summarize`, {
        method: 'POST',
        timeoutMs: SUMMARIZE_TIMEOUT_MS,
      }),
    () => dispatch({ type: 'meeting/summarize', meetingId }),
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
