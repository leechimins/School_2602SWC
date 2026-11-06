import { clearAllTimers } from '../lib/timers.ts'
import { reduce, type Action } from './actions.ts'
import { SEED, SEED_VERSION, type DemoState } from './seed.ts'

// 목 저장소: 서버 대신 시연 데이터를 들고 있는 곳.
// /demo의 휴대폰 화면 두 개(iframe)는 같은 출처라 localStorage를 함께 쓴다.
// 한쪽이 바꾸면 BroadcastChannel로 알리고, 다른 쪽이 다시 읽어 같은 상태를 본다.

const KEY = 'teamplay-demo-state'
const channel = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel('teamplay-demo')
const listeners = new Set<() => void>()
let state: DemoState = load()
let revision = 0 // 데이터가 바뀐 횟수. 실서버에 쓴 뒤에도 올려 화면이 다시 불러오게 한다

function load(): DemoState {
  try {
    const saved = localStorage.getItem(KEY)
    if (saved) {
      const parsed = JSON.parse(saved) as DemoState
      if (parsed.version === SEED_VERSION) return parsed // 시드 모양이 바뀌었으면 옛 저장값은 버린다
    }
  } catch {
    /* 저장소가 막혀 있어도 시드로 시연을 이어 간다 */
  }
  return structuredClone(SEED)
}

function save() {
  try {
    localStorage.setItem(KEY, JSON.stringify(state))
  } catch {
    /* 저장에 실패해도 이 화면 안에서는 계속 동작한다 */
  }
}

function notify() {
  revision += 1
  listeners.forEach((fn) => fn())
}

/** useApi가 다시 불러올 때를 아는 값 */
export function getRevision() {
  return revision
}

/** 실서버에 쓰기를 마쳤을 때: 목 데이터는 그대로지만 화면들이 다시 불러오게 알린다 */
export function markChanged() {
  channel?.postMessage('changed')
  notify()
}

export function getState(): DemoState {
  return state
}

/** 데이터를 바꾸는 유일한 길. 무엇을 바꾸는지는 actions.ts의 액션 표에 모여 있다 */
export function dispatch(action: Action) {
  state = reduce(state, action) // 항상 새 객체 → useSyncExternalStore가 참조로 변화를 알아챈다
  save()
  channel?.postMessage('changed')
  notify()
}

/** 시연 장치의 "기본": 데이터·시연 시계·걸어 둔 타이머를 모두 처음으로 */
export function resetState() {
  clearAllTimers()
  state = structuredClone(SEED)
  save()
  channel?.postMessage('reset')
  notify()
}

export function subscribe(fn: () => void) {
  listeners.add(fn)
  return () => {
    listeners.delete(fn)
  }
}

if (channel) {
  channel.onmessage = (e: MessageEvent<string>) => {
    if (e.data === 'reset') clearAllTimers()
    state = load()
    notify()
  }
}
