import { useEffect, useRef } from 'react'
import styles from './ConfirmDialog.module.css'

type Props = {
  title: string // "'PPT 제작'을 삭제할까요?" — 제목 하나로 충분하게
  okLabel: string // 하는 일 이름: "삭제", "모두 확정", "로그아웃"
  danger?: boolean // 삭제류는 빨간 버튼
  onClose: (ok: boolean) => void
}

// 가운데 뜨는 확인 창(시스템 모달). 되돌릴 수 없거나 다른 팀원에게도 영향이 가는 동작에만 쓴다.
// 되돌릴 수 있는 동작은 묻지 않고 하고 스낵바로 [되돌리기]를, 입력이 필요하면 InputSheet를 쓴다.
// 물을 때만 그린다: {asking && <ConfirmDialog ... onClose={...} />}
export default function ConfirmDialog({ title, okLabel, danger = false, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (dialog && !dialog.open) dialog.showModal()
  }, [])

  return (
    // Esc로 닫으면 취소
    <dialog ref={ref} className={styles.dialog} onCancel={() => onClose(false)}>
      <h2 className={styles.title}>{title}</h2>
      <div className={styles.actions}>
        <button type="button" className="btn quiet" onClick={() => onClose(false)}>
          취소
        </button>
        <button type="button" className={`btn ${danger ? 'danger' : 'primary'}`} onClick={() => onClose(true)}>
          {okLabel}
        </button>
      </div>
    </dialog>
  )
}
