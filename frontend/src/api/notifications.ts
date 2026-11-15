import type { Id } from '../types/common.ts'
import type { ActivityLog, NoticeList } from '../types/notification.ts'
import { request, write } from './client.ts'
import { toActivity, toNoticeList, type ServerActivity, type ServerNoticeList } from './convert.ts'

// 알림·에이전트가 한 일·양보 기록. 할 일 알림은 할 일 상태에서 나오므로 할 일을 바꾸면 여기도 바뀐다.

export async function getNotices(roomId: Id): Promise<NoticeList> {
  return toNoticeList(await request<ServerNoticeList>(`/rooms/${roomId}/notifications`))
}

/** 읽음 처리: 개별 또는 모두 */
export function markNoticesRead(roomId: Id, noticeIds: Id[]): Promise<void> {
  return write(() => request<void>(`/rooms/${roomId}/notifications/read`, { method: 'POST', body: { ids: noticeIds.map(Number) } }))
}

/** 에이전트가 한 일(무엇을·왜)과 양보 기록. 양보 크기는 숫자 없이 조금/많이로만 온다 */
export async function getActivity(roomId: Id): Promise<ActivityLog> {
  return toActivity(await request<ServerActivity>(`/rooms/${roomId}/agent-log`))
}
