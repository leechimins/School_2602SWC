/** 시간 정하는 과정에서 발언 하나가 나오는 간격 */
export const UTTERANCE_MS = 1_600

/** setTimeout 대신 쓴다. 돌려받은 함수를 부르면 취소된다(useEffect 정리에 그대로 돌려주기 좋다) */
export function later(fn: () => void, ms: number): () => void {
  const id = setTimeout(fn, ms)
  return () => clearTimeout(id)
}
