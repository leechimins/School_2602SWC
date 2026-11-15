import { useSyncExternalStore } from 'react'
import { getIdentity, subscribeIdentity } from '../api/session.ts'
import type { Id } from '../types/common.ts'

// 지금 로그인한 사람. 로그인 전에는 App.tsx의 RequireLogin이 스플래시로 보내므로 화면 안에서는 늘 있다.

export type CurrentUser = {
  id: Id
  name: string
  isLeader: boolean
  roomId: Id
}

const NOBODY: CurrentUser = { id: '', name: '', isLeader: false, roomId: '' }

export function useCurrentUser(): CurrentUser {
  const me = useSyncExternalStore(subscribeIdentity, getIdentity)
  if (!me) return NOBODY
  return { id: me.id, name: me.name, isLeader: me.isLeader, roomId: me.roomId ?? '' }
}
