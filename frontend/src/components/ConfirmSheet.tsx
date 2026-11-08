import { useEffect, useRef, useState } from 'react'
import styles from './ConfirmSheet.module.css'

export type ConfirmResult = { ok: boolean; value: string }

type Props = {
  title: string // "이 할 일을 삭제할까요?"
  body: string // 무엇을 하는지
  okLabel: string // 하는 일 이름: "삭제", "막힘으로 바꾸기"
  danger?: boolean // 삭제류는 빨간 버튼
  irreversible?: boolean // "되돌릴 수 없습니다" 안내
  input?: { label: string; placeholder: string; required?: string } // 막힌 이유·피드백 한 줄. required는 비웠을 때 보일 안내
  onClose: (result: ConfirmResult) => void
}

// 다시 묻기 창: 아래에서 올라오는 시트. 되돌릴 수 없는 동작(삭제·발송)과 한 줄 입력이 필요한 동작에 쓴다.
// 물을 때만 그린다: {asking && <ConfirmSheet ... onClose={...} />}
export default function ConfirmSheet({ title, body, okLabel, danger = false, irreversible = true, input, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null)
  const [value, setValue] = useState('')
  const [missing, setMissing] = useState(false)

  // 그려질 때 바로 연다. 닫을 때는 부모가 이 컴포넌트를 빼면 된다
  useEffect(() => {
    const dialog = ref.current
    if (dialog && !dialog.open) dialog.showModal()
  }, [])

  const close = (ok: boolean) => {
    if (ok && input?.required && !value.trim()) return setMissing(true) // 창을 닫지 않고 아래에 안내
    onClose({ ok, value: value.trim() })
  }

  return (
    // Esc로 닫으면 취소
    <dialog ref={ref} className={styles.sheet} onCancel={() => close(false)}>
      <h2 className={styles.title}>{title}</h2>
      <p>{body}</p>
      {irreversible && <p className="meta">되돌릴 수 없습니다.</p>}
      {input && (
        <input
          className={`field ${styles.input}`}
          value={value}
          maxLength={40}
          placeholder={input.placeholder}
          aria-label={input.label}
          onChange={(e) => {
            setValue(e.target.value)
            setMissing(false)
          }}
        />
      )}
      {missing && (
        <p className={styles.missing} role="alert">
          {input?.required}
        </p>
      )}
      <div className={styles.actions}>
        <button type="button" className="btn quiet" onClick={() => close(false)}>
          취소
        </button>
        <button type="button" className={`btn ${danger ? 'danger' : 'primary'}`} onClick={() => close(true)}>
          {okLabel}
        </button>
      </div>
    </dialog>
  )
}
