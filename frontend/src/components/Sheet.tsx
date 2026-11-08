import { useEffect, useRef, type ReactNode } from 'react'
import styles from './Sheet.module.css'

type Props = {
  title: string
  children: ReactNode
  /** 아래 버튼 줄 (취소 | 저장) */
  actions: ReactNode
  onClose: () => void // Esc·바깥 누름
}

// 아래에서 올라오는 시트. 한 줄 입력·확인은 ConfirmSheet, 여러 칸을 고치는 폼은 이것을 쓴다.
// 열 때만 그린다: {open && <Sheet ... />}
export default function Sheet({ title, children, actions, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (dialog && !dialog.open) dialog.showModal()
  }, [])

  return (
    <dialog
      ref={ref}
      className={styles.sheet}
      onCancel={onClose}
      onClick={(e) => e.target === ref.current && onClose()} // 어두운 바깥을 누르면 닫는다
    >
      <h2 className={styles.title}>{title}</h2>
      <div className={styles.body}>{children}</div>
      <div className={styles.actions}>{actions}</div>
    </dialog>
  )
}
