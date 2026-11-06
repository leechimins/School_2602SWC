import { mockContext } from '../mock/context.ts'
import { buildHome, buildRoom } from '../mock/views.ts'
import type { Id } from '../types/common.ts'
import type { Home } from '../types/home.ts'
import type { Room } from '../types/room.ts'
import { request, withMock } from './client.ts'
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
