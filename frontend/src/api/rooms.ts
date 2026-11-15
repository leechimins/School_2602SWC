import type { Id } from '../types/common.ts'
import type { Home } from '../types/home.ts'
import type { InvitePreview, Room, RoomInput } from '../types/room.ts'
import { request, write } from './client.ts'
import { toHome, toInvitePreview, toRoom, type ServerHome, type ServerInvitePreview, type ServerRoom } from './convert.ts'

// 방(Room)과 홈(Home). 화면은 이 함수들만 부른다.

export async function getRoom(roomId: Id): Promise<Room> {
  return toRoom(await request<ServerRoom>(`/rooms/${roomId}`))
}

/** 방 만들기: 만든 사람이 팀장이 되고, 돌려받은 방의 초대 코드를 팀원에게 보낸다 */
export function createRoom(input: RoomInput): Promise<Room> {
  return write(async () =>
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
  )
}

/** 초대 코드로 방 미리보기: 들어가기 전에 방 이름과 인원만 보여 준다 */
export async function previewInvite(code: string): Promise<InvitePreview> {
  return toInvitePreview(await request<ServerInvitePreview>(`/rooms/by-invite-code/${encodeURIComponent(code.trim())}`))
}

/** 초대 코드로 방 들어가기. 이미 팀원(ALREADY_MEMBER)·정원 참(ROOM_FULL)은 서버 문구를 그대로 띄운다 */
export function joinRoom(code: string): Promise<Room> {
  return write(async () => toRoom(await request<ServerRoom>('/rooms/join', { method: 'POST', body: { invite_code: code.trim() } })))
}

export async function getHome(roomId: Id): Promise<Home> {
  // 홈 응답에는 방 이름이 없어 방 정보를 함께 받는다
  const [home, room] = await Promise.all([request<ServerHome>(`/rooms/${roomId}/home`), request<ServerRoom>(`/rooms/${roomId}`)])
  const me = room.members.find((m) => m.is_me)
  return toHome(home, room.name, { id: String(me?.user_id ?? ''), name: me?.name ?? '' })
}
