import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client.ts'
import { NOTICE_EVENT, type NoticeItem } from '../lib/notice.ts'
import { later } from '../lib/timers.ts'
import styles from './Toast.module.css'

const TOAST_MS = 2_500 // 결과만 알리는 한 줄
const SNACK_MS = 5_000 // [되돌리기]가 있는 한 줄: 누를 시간을 더 준다
const ERROR_MS = 4_000

// 화면 맨 아래(하단 탭 바로 위)에 잠깐 뜨는 한 줄. 앱 틀(AppShell)에 하나만 둔다.
// ① showNotice로 보낸 토스트·스낵바 ② 결과를 기다리지 않는 쓰기(상태 칩·담당자 고르기)의 실패.
//    그런 쓰기는 오류를 받는 곳이 없어 unhandledrejection으로 올라오므로 여기서 받아 알린다.
//    오류를 직접 받아 보여 주는 화면(할 일 추가·수락·거절 등)은 여기까지 오지 않아 두 번 뜨지 않는다.
export default function Toast() {
  const [item, setItem] = useState<NoticeItem | null>(null)
  const current = useRef<NoticeItem | null>(null)

  // 지금 알림을 내린다. 되돌리지 않고 끝나면 미뤄 둔 반영(onExpire)을 한다
  const finish = (undone: boolean) => {
    const done = current.current
    current.current = null
    setItem(null)
    if (done && !undone) done.onExpire?.()
  }

  useEffect(() => {
    const show = (next: NoticeItem) => {
      finish(false) // 앞 알림의 반영을 마저 하고 바꾼다
      current.current = next
      setItem(next)
    }
    const onNotice = (e: Event) => show((e as CustomEvent<NoticeItem>).detail)
    const onReject = (e: PromiseRejectionEvent) => {
      if (!(e.reason instanceof ApiError)) return
      e.preventDefault()
      show({ message: `반영하지 못했어요. ${e.reason.message}` })
    }
    window.addEventListener(NOTICE_EVENT, onNotice)
    window.addEventListener('unhandledrejection', onReject)
    return () => {
      window.removeEventListener(NOTICE_EVENT, onNotice)
      window.removeEventListener('unhandledrejection', onReject)
      finish(false) // 틀이 바뀌어 사라질 때도 미뤄 둔 반영은 한다
    }
  }, [])

  useEffect(() => {
    if (item === null) return
    const ms = item.undo ? SNACK_MS : item.message.startsWith('반영하지 못했어요') ? ERROR_MS : TOAST_MS
    return later(() => finish(false), ms)
  }, [item])

  if (item === null) return null
  return (
    <div className={styles.toast} role={item.undo ? 'status' : 'alert'}>
      <span>{item.message}</span>
      {item.undo && (
        <button
          type="button"
          className={styles.undo}
          onClick={() => {
            item.undo?.()
            finish(true)
          }}
        >
          되돌리기
        </button>
      )}
    </div>
  )
}
