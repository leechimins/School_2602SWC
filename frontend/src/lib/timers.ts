// 시연 중에 걸어 둔 타이머(발언 하나씩 보여 주기, 토스트 닫기 등)를 한 곳에서 관리한다.
// 시연 장치의 "기본"을 누르면 데이터와 함께 모두 지운다. 안 지우면 초기화 뒤에 지난 장면의 토스트가 뜬다(목업 버그 ④).
/** 시간 정하는 과정에서 발언 하나가 나오는 간격. 목 서버가 조율을 끝내는 시각도 이 값으로 맞춘다 */
export const UTTERANCE_MS = 1_600

const pending = new Set<ReturnType<typeof setTimeout>>()

/** setTimeout 대신 쓴다. 돌려받은 함수를 부르면 취소된다 */
export function later(fn: () => void, ms: number): () => void {
  const id = setTimeout(() => {
    pending.delete(id)
    fn()
  }, ms)
  pending.add(id)
  return () => {
    clearTimeout(id)
    pending.delete(id)
  }
}

export function clearAllTimers() {
  pending.forEach(clearTimeout)
  pending.clear()
}
