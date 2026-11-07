import type { Id } from '../types/common.ts'
import { ApiError, fallBackToMock, isRealServer, request } from './client.ts'

// 실서버에서 "나는 누구"를 들고 있는 곳. 로그인한 뒤 GET /me로 받은 서버 번호를 쓴다.
//
// 목 데이터의 ID(room-1, u-minji)는 서버가 모른다. 그대로 보내면 /rooms/room-1/home이 400이고,
// 담당자 비교(u-minji와 2)도 늘 틀린다. 그래서 실서버 모드에서는 화면이 이 번호만 쓴다(useCurrentUser).

export type Identity = {
  id: Id
  name: string
  roomId: Id | null // 아직 방에 안 들어갔으면 null
  isLeader: boolean
}

type ServerMe = {
  user_id: number
  name: string
  rooms: { id: number; name: string; is_leader: boolean }[]
}

let identity: Identity | null = null
const listeners = new Set<() => void>()

export function getIdentity(): Identity | null {
  return identity
}

export function subscribeIdentity(fn: () => void): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

function set(next: Identity | null) {
  identity = next
  listeners.forEach((fn) => fn())
}

/** 개발용 로그인: 이름만 보내면 그 사람이 된다(서버 POST /sessions). 구글 로그인이 붙으면 시작 화면이 그 길을 쓴다 */
async function devLogin(name: string): Promise<void> {
  await request('/sessions', { method: 'POST', body: { name } })
}

/** 지금 쿠키의 주인. 로그인 안 했으면 null */
async function loadMe(): Promise<Identity | null> {
  try {
    const me = await request<ServerMe>('/me')
    // 방은 첫 번째 하나만 쓴다. 지금 화면이 방 하나를 전제로 그려져 있다
    const room = me.rooms[0]
    return {
      id: String(me.user_id),
      name: me.name,
      roomId: room ? String(room.id) : null,
      isLeader: room?.is_leader ?? false,
    }
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return null
    throw e
  }
}

/**
 * 이 사람으로 로그인하고 서버 번호를 받는다. 앱이 처음 뜰 때와 시연 장치가 사람을 바꿀 때 부른다.
 *
 * 서버가 안 닿으면(네트워크·5xx·주소 틀림) 목으로 돌아간다 — "서버가 죽으면 같은 목 데이터로 이어 간다"는
 * client.ts의 원칙과 같다. 이름이 서버에 없으면(404) 로그인 안 한 상태로 둔다.
 */
export async function signIn(name: string | null): Promise<void> {
  if (!isRealServer()) return
  try {
    if (name) await devLogin(name)
    set(await loadMe())
  } catch (e) {
    if (e instanceof ApiError && e.status < 500 && e.code !== 'UNKNOWN') {
      console.warn('[session] 로그인하지 못했어요', e)
      set(null)
      return
    }
    console.warn('[session] 서버에 닿지 않아 목 데이터로 이어 가요', e)
    fallBackToMock()
    set(null)
  }
}
