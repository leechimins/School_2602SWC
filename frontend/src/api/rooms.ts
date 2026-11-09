import { mockContext } from '../mock/context.ts'
import { dispatch } from '../mock/store.ts'
import { buildHome, buildRoom } from '../mock/views.ts'
import type { Id } from '../types/common.ts'
import type { Home } from '../types/home.ts'
import type { InvitePreview, Room, RoomInput } from '../types/room.ts'
import { ApiError, request, withMock, withMockWrite } from './client.ts'
import { toHome, toInvitePreview, toRoom, type ServerHome, type ServerInvitePreview, type ServerRoom } from './convert.ts'

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

// 목 모드의 초대 코드 확인. 서버처럼 대소문자를 가리지 않는다(room/router.py _room_by_code)
function mockRoomByCode(code: string) {
  const { s } = mockContext()
  if (code.trim().toUpperCase() !== s.room.inviteCode) throw new ApiError(404, 'NOT_FOUND', '그 초대 코드의 방이 없어요.')
  return s
}

/** 초대 코드로 방 미리보기: 들어가기 전에 방 이름과 인원만 보여 준다 */
export function previewInvite(code: string): Promise<InvitePreview> {
  return withMock(
    async () => toInvitePreview(await request<ServerInvitePreview>(`/rooms/by-invite-code/${encodeURIComponent(code.trim())}`)),
    () => {
      // 시연: 시드는 네 명이 다 들어와 있어서, 보는 사람이 지금 들어오는 것처럼 본인은 빼고 센다
      const s = mockRoomByCode(code)
      return { name: s.room.name, memberCount: s.room.memberCount, joinedCount: s.members.length - 1 }
    },
  )
}

/** 초대 코드로 방 들어가기. 이미 팀원(ALREADY_MEMBER)·정원 참(ROOM_FULL)은 서버 문구를 그대로 띄운다 */
export function joinRoom(code: string): Promise<Room> {
  return withMockWrite(
    async () => toRoom(await request<ServerRoom>('/rooms/join', { method: 'POST', body: { invite_code: code.trim() } })),
    () => {
      // 목 시드는 팀원 네 명이 이미 다 들어와 있어 방만 확인하고 그 방을 돌려준다
      mockRoomByCode(code)
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
