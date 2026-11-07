import dayjs, { type Dayjs } from 'dayjs'
import { useSyncExternalStore } from 'react'
import { isRealServer } from '../api/client.ts'
import { dispatch, getState, subscribe } from '../mock/store.ts'

// 앱에서 "지금"을 아는 유일한 곳. 시연 시계를 옮기면 두 휴대폰 화면의 시각이 함께 바뀐다.
// 시연 시각은 멈춰 있는 값이라 같은 장면을 몇 번 돌려도 같은 화면이 나온다.
// 컴포넌트는 useClock(), 컴포넌트 밖(목 API 등)은 getNow()만 쓰고 new Date()·Date.now()를 직접 부르지 않는다.

export function getNow(): Dayjs {
  return isRealServer() ? dayjs() : dayjs(getState().clockNow)
}

export function useClock(): Dayjs {
  const clockNow = useSyncExternalStore(subscribe, () => getState().clockNow)
  // 실서버면 서버와 같은 시계를 쓴다. 목 시계(11/10에 멈춤)로 묶으면 서버가 "내일"이라고 준 할 일이
  // "기한 지남"으로 보인다.
  // shortcut: 서버 시연 시계를 아직 못 읽어 실제 시각을 쓴다(서버도 시계를 안 옮기면 실제 시각).
  // GET /demo/clock이 생기면 그 값을 쓰고, 시연 장치의 시계 버튼도 서버 시계를 옮기게 바꾼다.
  return isRealServer() ? dayjs() : dayjs(clockNow)
}

/** 시연 시계 넘기기(양수)·되돌리기(음수) */
export function moveClock(minutes: number) {
  dispatch({ type: 'clock/move', minutes })
}

/** 시연 시계를 처음 시각으로 */
export function resetClock() {
  dispatch({ type: 'clock/reset' })
}
