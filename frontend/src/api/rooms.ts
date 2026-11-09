import { mockContext } from '../mock/context.ts'
import { dispatch } from '../mock/store.ts'
import { buildHome, buildRoom } from '../mock/views.ts'
import type { Id } from '../types/common.ts'
import type { Home } from '../types/home.ts'
import type { InvitePreview, Room, RoomInput } from '../types/room.ts'
import { request, withMock, withMockWrite } from './client.ts'
import { toHome, toRoom, type ServerHome, type ServerRoom } from './convert.ts'

// 방(Room)과 홈(Home). 화면은 이 함수들만 부른다.

export function getRoom(roomId: Id): Promise<Room> {
  return withMock(
    async () => toRoom(await request<ServerRoom>(`/rooms/${roomId}`)),
    () => {
      const { s, viewer } = mockContext()
      return buildRoom(s, viewer)
    },
  )
}

/** 방 만들기: 만든 사람이 팀장이 되고, 돌려받은 방의 초대 코드를 팀원에게 보낸다 */
export function createRoom(input: RoomInput): Promise<Room> {
  return withMockWrite(
    async () =>
      toRoom(
        await request<ServerRoom>('/rooms', {
          method: 'POST',
          body: {
            name: input.name,
            description: input.description,
            start_date: input.startDate,
            due_date: input.dueDate,
            member_count: input.memberCount,
          },
        }),
      ),
    () => {
      dispatch({ type: 'room/create', input })
      const { s, viewer } = mockContext()
      return buildRoom(s, viewer)
    },
  )
}

/** 초대 코드로 방 미리보기. 들어가기 전에 방 이름과 인원을 보여 준다. 코드는 대소문자를 가리지 않는다 */
export function previewInvite(code: string): Promise<InvitePreview> {
  return withMock(
    async () => {
      const r = await request<{ name: string; member_count: number; joined_count: number }>(
        `/rooms/by-invite-code/${encodeURIComponent(code)}`,
      )
      return { name: r.name, memberCount: r.member_count, joinedCount: r.joined_count }
    },
    () => {
      const { s, viewer } = mockContext()
      const room = buildRoom(s, viewer)
      return { name: room.name, memberCount: room.memberCount, joinedCount: room.joinedCount }
    },
  )
}

/** 초대 코드로 팀원이 된다. 이미 팀원이면 409 ALREADY_MEMBER, 정원이 차면 409 ROOM_FULL */
export function joinRoom(code: string): Promise<Room> {
  return withMockWrite(
    async () => toRoom(await request<ServerRoom>('/rooms/join', { method: 'POST', body: { invite_code: code } })),
    () => {
      const { s, viewer } = mockContext()
      return buildRoom(s, viewer)
    },
  )
}

export function getHome(roomId: Id): Promise<Home> {
  return withMock(
    async () => {
      // 홈 응답에는 방 이름이 없어 방 정보를 함께 받는다
      const [home, room] = await Promise.all([
        request<ServerHome>(`/rooms/${roomId}/home`),
        request<ServerRoom>(`/rooms/${roomId}`),
      ])
      const me = room.members.find((m) => m.is_me)
      return toHome(home, room.name, { id: String(me?.user_id ?? ''), name: me?.name ?? '' })
    },
    () => {
      const { s, viewer, now } = mockContext()
      return buildHome(s, viewer, now)
    },
  )
}
