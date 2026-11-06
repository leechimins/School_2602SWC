import { useEffect, useReducer, useRef, type MouseEvent, type PointerEvent, type ReactNode } from 'react'
import { formatMD } from '../lib/date.ts'
import { later } from '../lib/timers.ts'
import { TASK_STATUS_TONE } from '../lib/tones.ts'
import { TASK_STATUSES, type Task, type TaskStatus } from '../types/task.ts'
import Badge from './Badge.tsx'
import badge from './Badge.module.css'
import ConfirmSheet from './ConfirmSheet.tsx'
import styles from './TaskRow.module.css'

type Props = {
  task: Task
  /** 상태 바꾸기. 막힘이면 막힌 이유 한 줄(비워도 됨)이 함께 온다 */
  onStatusChange: (task: Task, status: TaskStatus, reason: string | null) => void
  /** 길게 누르기(0.5초)·우클릭 = 고치기 패널 열기 */
  onEdit?: (task: Task) => void
  /** 행 아래에 붙는 것 (담당자 지정 칸, 고치기 패널) */
  children?: ReactNode
}

// 행 안의 누름 동작을 액션 표로 모은다
type UiState = { menuOpen: boolean; askingBlocked: boolean }
type UiAction = { type: 'menu/toggle' } | { type: 'menu/close' } | { type: 'blocked/ask' } | { type: 'blocked/close' }

function reduceUi(state: UiState, action: UiAction): UiState {
  switch (action.type) {
    case 'menu/toggle':
      return { ...state, menuOpen: !state.menuOpen }
    case 'menu/close':
      return { ...state, menuOpen: false }
    case 'blocked/ask':
      return { menuOpen: false, askingBlocked: true }
    case 'blocked/close':
      return { ...state, askingBlocked: false }
  }
}

const LONG_PRESS_MS = 500

// 할 일 한 줄 (팀 할 일·내 할 일·홈 공통): 체크 · 제목(늦음·막힘 뱃지) | 기한 · 상태 칩
// 상태 칩과 완료 체크는 담당자만 쓴다. 남의 일은 체크가 회색으로 막혀 있지만, 완료면 체크 표시는 보인다(목업 버그 ⑤).
export default function TaskRow({ task, onStatusChange, onEdit, children }: Props) {
  const [ui, send] = useReducer(reduceUi, { menuOpen: false, askingBlocked: false })
  const rowRef = useRef<HTMLLIElement>(null)
  const cancelPress = useRef<(() => void) | null>(null)
  const mine = task.canChangeStatus
  const done = task.status === '완료'

  // 메뉴 바깥을 누르면 닫는다
  useEffect(() => {
    if (!ui.menuOpen) return
    const close = (e: globalThis.PointerEvent) => {
      if (!rowRef.current?.contains(e.target as Node)) send({ type: 'menu/close' })
    }
    document.addEventListener('pointerdown', close)
    return () => document.removeEventListener('pointerdown', close)
  }, [ui.menuOpen])

  const pick = (status: TaskStatus) => {
    if (status === '막힘' && task.status !== '막힘') return send({ type: 'blocked/ask' })
    send({ type: 'menu/close' })
    if (status !== task.status) onStatusChange(task, status, null)
  }

  const stopPress = () => {
    cancelPress.current?.()
    cancelPress.current = null
  }
  const press = onEdit && {
    onPointerDown: (e: PointerEvent) => {
      if (e.button !== 0 || (e.target as HTMLElement).closest('button')) return
      cancelPress.current = later(() => onEdit(task), LONG_PRESS_MS)
    },
    onPointerUp: stopPress,
    onPointerLeave: stopPress,
    onPointerCancel: stopPress,
    onContextMenu: (e: MouseEvent) => {
      e.preventDefault() // 노트북 시연: 우클릭도 고치기
      stopPress()
      onEdit(task)
    },
  }

  const late = task.isLate
  const blockedBadge = task.status === '막힘' && !mine // 내 일은 상태 칩이 이미 "막힘"을 보여 준다

  return (
    <li ref={rowRef} className={styles.row} data-done={done}>
      <div className={styles.head} {...press}>
        <div className={styles.title}>
          <button
            type="button"
            className={styles.check}
            disabled={!mine}
            aria-label={`${task.title} 완료 표시`}
            aria-pressed={done}
            onClick={() => onStatusChange(task, done ? '시작 전' : '완료', null)}
          />
          <span className={styles.name}>
            {task.title}
            {late && <Badge tone="danger">늦음</Badge>}
            {blockedBadge && <Badge tone="warn">막힘</Badge>}
          </span>
        </div>
        <div className={styles.right}>
          {task.dueDate && <span className="meta num">{formatMD(task.dueDate)}</span>}
          {mine && (
            <button
              type="button"
              className={`${badge.badge} ${badge[TASK_STATUS_TONE[task.status]]} ${styles.chip}`}
              aria-haspopup="menu"
              aria-expanded={ui.menuOpen}
              aria-label={`상태 ${task.status}, 눌러서 바꾸기`}
              onClick={() => send({ type: 'menu/toggle' })}
            >
              {task.status}
            </button>
          )}
          {ui.menuOpen && (
            <div className={styles.menu} role="menu">
              {TASK_STATUSES.map((status) => (
                <button
                  key={status}
                  type="button"
                  role="menuitemradio"
                  aria-checked={status === task.status}
                  onClick={() => pick(status)}
                >
                  <Badge tone={TASK_STATUS_TONE[status]}>{status}</Badge>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      {children}
      {ui.askingBlocked && (
        <ConfirmSheet
          title="막힘으로 바꿀까요?"
          body="팀에 바로 알려요. 막힌 이유를 한 줄 남기면 알림에 같이 보여요. 비워 둬도 돼요."
          okLabel="막힘으로 바꾸기"
          irreversible={false}
          input={{ label: '막힌 이유', placeholder: '예: 인터뷰 녹취가 아직 안 왔어요' }}
          onClose={({ ok, value }) => {
            send({ type: 'blocked/close' })
            if (ok) onStatusChange(task, '막힘', value || null)
          }}
        />
      )}
    </li>
  )
}
