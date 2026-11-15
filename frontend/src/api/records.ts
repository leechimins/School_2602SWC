import type { Id } from '../types/common.ts'
import type { MeetingDetail, RecordInput, SuggestionPatch } from '../types/meeting.ts'
import { request, write } from './client.ts'
import { toMeetingDetail, toServerMode, type ServerMeetingDetail } from './convert.ts'

// 회의 기록·회의록·할 일 제안. 장면 2의 앞부분(회의에서 할 일로)이 여기서 나온다.

/** 회의록: 원문 + 요약 + 그 회의에서 확정된 할 일 + 확정 전 제안 */
export async function getMeeting(roomId: Id, meetingId: Id): Promise<MeetingDetail> {
  return toMeetingDetail(await request<ServerMeetingDetail>(`/rooms/${roomId}/meetings/${meetingId}`))
}

/** 회의 기록 시작: 잡힌 회의가 없어도 주제 한 줄로 바로 연다. 새 회의 ID를 돌려준다 */
export function createMeeting(roomId: Id, input: RecordInput): Promise<Id> {
  return write(async () => {
    const r = await request<{ id: number }>(`/rooms/${roomId}/meetings`, {
      method: 'POST',
      body: { meeting_id: input.meetingId && Number(input.meetingId), topic: input.topic, mode: toServerMode(input.mode) },
    })
    return String(r.id)
  })
}

/**
 * 원문 저장. 한 줄에 한 말, "이름: 말"이면 말한 사람으로 읽는다.
 * 원문을 먼저 저장하고 정리(summarize)는 따로 부른다 — 정리가 실패해도 원문은 남는다.
 */
export function writeTranscript(roomId: Id, meetingId: Id, text: string): Promise<void> {
  return write(() => request<void>(`/rooms/${roomId}/meetings/${meetingId}/transcript`, { method: 'PUT', body: { text } }))
}

/** 녹음 시작: 서버에 받아적는 중으로 표시한다. 확정된 회의만 되고, 다시 불러도 그대로다 */
export async function startRecording(roomId: Id, meetingId: Id): Promise<void> {
  await request(`/rooms/${roomId}/meetings/${meetingId}/recording/start`, { method: 'POST' })
}

const UPLOAD_TIMEOUT_MS = 130_000 // 서버가 AI로 받아적는 데 최대 2분

/**
 * 녹음 파일을 올리면 서버가 받아적어 목소리마다 A·B… 라벨을 붙인 원문을 돌려준다.
 * 실패해도 서버는 받아적는 중 그대로라 같은 녹음으로 다시 올릴 수 있다
 */
export async function uploadRecording(roomId: Id, meetingId: Id, audio: Blob): Promise<MeetingDetail> {
  return toMeetingDetail(
    await request<ServerMeetingDetail>(`/rooms/${roomId}/meetings/${meetingId}/recording/audio`, {
      method: 'POST',
      audio,
      timeoutMs: UPLOAD_TIMEOUT_MS,
    }),
  )
}

/** 말한 사람 정하기: 목소리 라벨마다 팀원 한 명(null은 모름). 그 라벨의 모든 줄에 반영된다 */
export function mapSpeakers(roomId: Id, meetingId: Id, labels: Record<string, Id | null>): Promise<void> {
  const body = { labels: Object.fromEntries(Object.entries(labels).map(([label, who]) => [label, who && Number(who)])) }
  return write(() => request<void>(`/rooms/${roomId}/meetings/${meetingId}/speaker-mapping`, { method: 'PUT', body }))
}

const SUMMARIZE_TIMEOUT_MS = 25_000 // 정리는 20초까지 걸린다(브리프 "기다림과 빈 화면")

/** 회의록 정리 + 할 일 뽑기(AI). 실패하면 "잠시 후 다시 해 주세요." 한 줄과 다시 하기로 이어 간다 */
export function summarizeMeeting(roomId: Id, meetingId: Id): Promise<void> {
  return write(() =>
    request<void>(`/rooms/${roomId}/meetings/${meetingId}/summarize`, { method: 'POST', timeoutMs: SUMMARIZE_TIMEOUT_MS }),
  )
}

/** 할 일 제안 한꺼번에 확정. 담당자가 없어도 확정된다 */
export function confirmSuggestions(roomId: Id, suggestionIds: Id[]): Promise<void> {
  return write(() =>
    request<void>(`/rooms/${roomId}/suggestions/confirm`, { method: 'POST', body: { suggestion_ids: suggestionIds.map(Number) } }),
  )
}

export function editSuggestion(roomId: Id, suggestionId: Id, patch: SuggestionPatch): Promise<void> {
  const body = {
    title: patch.title,
    assignee_user_id: patch.assigneeId === undefined ? undefined : patch.assigneeId && Number(patch.assigneeId),
    due_date: patch.dueDate,
  }
  return write(() => request<void>(`/rooms/${roomId}/suggestions/${suggestionId}`, { method: 'PATCH', body }))
}

/** 제안 삭제. 되돌릴 수 없어 화면에서 한 번 더 묻는다 */
export function dismissSuggestion(roomId: Id, suggestionId: Id): Promise<void> {
  return write(() => request<void>(`/rooms/${roomId}/suggestions/${suggestionId}`, { method: 'DELETE' }))
}
