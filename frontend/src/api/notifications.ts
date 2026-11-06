import { mockContext } from '../mock/context.ts'
import { dispatch } from '../mock/store.ts'
import { buildActivity, buildNotices } from '../mock/views.ts'
import type { Id } from '../types/common.ts'
import type { ActivityLog, NoticeList } from '../types/notification.ts'
import { request, withMock, withMockWrite } from './client.ts'
import { toNoticeList, type ServerNoticeList } from './convert.ts'

// 알림·에이전트가 한 일·양보 기록. 할 일 알림은 할 일 상태에서 나오므로 할 일을 바꾸면 여기도 바뀐다.

export function getNotices(roomId: Id): Promise<NoticeList> {
  return withMock(
    async () => toNoticeList(await request<ServerNoticeList>(`/rooms/${roomId}/notifications`)),
    () => {
      const { s, viewer, now } = mockContext()
      return buildNotices(s, viewer, now)
    },
  )
}

/** 읽음 처리: 개별 또는 모두 */
export function markNoticesRead(roomId: Id, noticeIds: Id[]): Promise<void> {
  return withMockWrite(
    () => request<void>(`/rooms/${roomId}/notifications/read`, { method: 'POST', body: { ids: noticeIds.map(Number) } }),
    () => dispatch({ type: 'notice/read', userId: mockContext().viewer, noticeIds }),
  )
}

/** 에이전트가 한 일(무엇을·왜)과 양보 기록. 응답 모양이 서버에 아직 없어 목 데이터만 쓴다 */
export function getActivity(_roomId: Id): Promise<ActivityLog> {
  return Promise.resolve(buildActivity(mockContext().s))
}
