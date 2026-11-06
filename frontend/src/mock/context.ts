import { getNow } from '../hooks/useClock.ts'
import { getCurrentUserId } from '../hooks/useCurrentUser.ts'
import { getState } from './store.ts'

/** 목 API가 서버 대신 답할 때 필요한 것: 데이터, 보는 사람, 시연 시계의 지금 */
export function mockContext() {
  return { s: getState(), viewer: getCurrentUserId(), now: getNow() }
}
