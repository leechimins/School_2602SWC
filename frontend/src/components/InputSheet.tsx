import { useEffect, useRef, useState } from 'react'
import styles from './InputSheet.module.css'

export type InputResult = { ok: boolean; value: string }

type Props = {
  title: string // "회의 주제 입력"
  body?: string // 무엇을 하는지. 제목으로 충분하면 비운다
  okLabel: string // 하는 일 이름: "기록 시작", "막힘으로 바꾸기"
  input?: { label: string; placeholder: string; required?: string } // 막힌 이유·피드백 한 줄. required는 비웠을 때 보일 안내
  onClose: (result: InputResult) => void
}

// 입력 시트: 한 줄 입력이 필요한 동작(회의 주제·막힌 이유·거절 이유)에 쓴다. 아래에서 올라와 키보드와 함께 보인다.
// 입력 없이 묻기만 할 때는 ConfirmDialog. 물을 때만 그린다: {asking && <InputSheet ... onClose={...} />}
export default function InputSheet({ title, body, okLabel, input, onClose }: Props) {
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
      {body && <p>{body}</p>}
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
        <button type="button" className="btn primary" onClick={() => close(true)}>
          {okLabel}
        </button>
      </div>
    </dialog>
  )
}
