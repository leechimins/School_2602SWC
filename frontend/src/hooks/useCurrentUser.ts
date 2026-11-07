import { useSyncExternalStore } from 'react'
import { getState, subscribe as subscribeStore } from '../mock/store.ts'
import type { Id } from '../types/common.ts'

// 지금 이 휴대폰 화면을 보는 사람.
// /demo의 iframe은 src="/?user=u-minji"처럼 주소로 사람을 정한다. 앱이 처음 뜰 때 한 번 읽고, 화면을 옮겨도 그대로 둔다.
// 주소에 없거나 모르는 ID면 팀장으로 본다. 화면 코드에 사람 ID를 직접 쓰지 않는다.

export type CurrentUser = {
  id: Id
  name: string
  isLeader: boolean
  roomId: Id
}

const listeners = new Set<() => void>()
let userId: Id | null = new URLSearchParams(window.location.search).get('user')

/** 컴포넌트 밖(목 API)에서 보는 사람. 목록에 없는 ID면 팀장 (사람을 바꿔도 화면이 깨지지 않게, 목업 버그 ③) */
export function getCurrentUserId(): Id {
  const { members, room } = getState()
  return members.some((m) => m.id === userId) ? (userId as Id) : room.leaderId
}

/** 시연 장치의 사용자 바꾸기 */
export function switchUser(id: Id) {
  userId = id
  listeners.forEach((fn) => fn())
}

// /demo 패널이 휴대폰 화면의 주소를 ?user=…로 바꾸고 popstate를 보내면 새로고침 없이 사람을 바꾼다.
// 새로고침하면 조율 재생 타이머가 끊기므로 이 길을 쓴다. 앱 안 이동은 ?user를 떼므로 없을 때는 그대로 둔다.
window.addEventListener('popstate', () => {
  const next = new URLSearchParams(window.location.search).get('user')
  if (next && next !== userId) switchUser(next)
})

function subscribe(fn: () => void) {
  listeners.add(fn)
  const unsubscribeStore = subscribeStore(fn) // 초기화로 팀원이 바뀌어도 다시 계산
  return () => {
    listeners.delete(fn)
    unsubscribeStore()
  }
}

export function useCurrentUser(): CurrentUser {
  const id = useSyncExternalStore(subscribe, getCurrentUserId)
  const { members, room } = getState()
  const me = members.find((m) => m.id === id)
  return { id, name: me?.name ?? '', isLeader: id === room.leaderId, roomId: room.id }
}
