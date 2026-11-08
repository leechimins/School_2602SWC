import { useEffect, useState } from 'react'
import { ApiError } from '../api/client.ts'
import { later } from '../lib/timers.ts'
import styles from './WriteFailNotice.module.css'

const SHOW_MS = 4_000

// 상태 칩·담당자 고르기처럼 결과를 기다리지 않는 쓰기는 실패해도 화면이 그대로라 "조용히 안 바뀐" 것처럼 보인다.
// 그런 쓰기는 오류를 받는 곳이 없어 unhandledrejection으로 올라오므로, 여기서 받아 아래에 한 줄로 알린다.
// 오류를 직접 받아 보여 주는 화면(할 일 추가·수락·거절 등)은 여기까지 오지 않아 두 번 뜨지 않는다.
export default function WriteFailNotice() {
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    const onReject = (e: PromiseRejectionEvent) => {
      if (!(e.reason instanceof ApiError)) return
      e.preventDefault()
      setMessage(e.reason.message)
    }
    window.addEventListener('unhandledrejection', onReject)
    return () => window.removeEventListener('unhandledrejection', onReject)
  }, [])

  useEffect(() => {
    if (message === null) return
    return later(() => setMessage(null), SHOW_MS)
  }, [message])

  if (message === null) return null
  return (
    <p className={styles.notice} role="alert">
      반영하지 못했어요. {message}
    </p>
  )
}
