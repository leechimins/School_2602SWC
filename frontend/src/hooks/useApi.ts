import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'
import { messageOf } from '../api/client.ts'
import { getRevision, subscribe } from '../mock/store.ts'

export type ApiState<T> =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: T }

/**
 * api/ 함수를 불러 불러오기·실패·다시 하기 상태를 준다.
 * deps가 바뀌거나 데이터가 바뀌면(다른 휴대폰 화면의 변경, 시연 시계 이동 포함) 다시 부른다.
 * 다시 부르는 동안에는 지난 데이터를 그대로 두어 화면이 깜빡이지 않는다.
 */
export function useApi<T>(fn: () => Promise<T>, deps: readonly unknown[]): ApiState<T> & { reload: () => void } {
  const [state, setState] = useState<ApiState<T>>({ status: 'loading' })
  const [retry, setRetry] = useState(0)
  const revision = useSyncExternalStore(subscribe, getRevision)

  useEffect(() => {
    let alive = true // 늦게 온 지난 응답이 새 응답을 덮지 않게
    fn().then(
      (data) => alive && setState({ status: 'ready', data }),
      (e: unknown) => alive && setState({ status: 'error', message: messageOf(e) }),
    )
    return () => {
      alive = false
    }
    // fn은 매번 새로 만들어지므로 deps로 다시 부를 때를 정한다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, revision, retry])

  const reload = useCallback(() => setRetry((n) => n + 1), [])
  return { ...state, reload }
}
