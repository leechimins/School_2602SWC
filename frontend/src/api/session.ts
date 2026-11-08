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

/** 개발용 로그인: 이름만 보내면 그 사람이 된다(서버 POST /sessions). 시연 장치와 "시연 계정으로 둘러보기"가 쓴다 */
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
 * 이 사람으로 로그인하고 서버 번호를 받는다. name이 null이면 로그인은 하지 않고 지금 쿠키의 주인만 확인한다.
 * 스플래시는 null로(구글 로그인 쿠키 확인), 시연 장치(?user=)는 이름으로 부른다.
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

type GoogleLoginOut = { user_id: number; name: string; is_new: boolean }

/**
 * 구글 로그인 버튼이 준 ID 토큰으로 로그인한다(서버 POST /sessions/google).
 * 처음 온 사람이면 true — 화면이 방 만들기로 보낸다. 실패하면 ApiError를 그대로 던진다(화면이 message를 띄운다).
 */
export async function signInWithGoogle(credential: string): Promise<boolean> {
  const out = await request<GoogleLoginOut>('/sessions/google', { method: 'POST', body: { credential } })
  set(await loadMe())
  return out.is_new
}

/** 로그아웃. 서버가 안 닿아도 이 화면에서는 로그인 안 한 상태로 둔다 */
export async function signOut(): Promise<void> {
  if (isRealServer()) await request('/sessions', { method: 'DELETE' }).catch(() => undefined)
  set(null)
}
