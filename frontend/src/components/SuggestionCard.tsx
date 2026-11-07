import { useState } from 'react'
import type { Suggestion, SuggestionPatch } from '../types/meeting.ts'
import type { Member } from '../types/room.ts'
import AiMark from './AiMark.tsx'
import ConfirmSheet from './ConfirmSheet.tsx'
import styles from './SuggestionCard.module.css'
import { AssigneeSelect, DueInput } from './TaskFields.tsx'

type Props = {
  suggestion: Suggestion
  members: Member[]
  onEdit: (patch: SuggestionPatch) => void
  onConfirm: () => void
  onDismiss: () => void
}

// 할 일 제안 카드(업무 배정 검토): ① AI 제안 + 제목 ② 담당자 · 기한 | 삭제 · 확정
// 담당자만 정해 두고 확정은 나중에 해도 된다 — 확정 전까지는 "AI 제안" 표시가 남는다.
export default function SuggestionCard({ suggestion: g, members, onEdit, onConfirm, onDismiss }: Props) {
  // 제목은 글자를 칠 때마다 저장하지 않고 칸을 벗어날 때 한 번 저장한다.
  // 그래서 제목을 고치고 바로 옆 "확정"을 눌러도 다시 그리기에 클릭이 묻히지 않는다(목업 버그 ②)
  const [title, setTitle] = useState(g.title)
  const [asking, setAsking] = useState(false)

  const saveTitle = () => {
    const next = title.trim()
    if (!next) return setTitle(g.title) // 비우면 원래 제목으로
    if (next !== g.title) onEdit({ title: next })
  }

  return (
    <article className={styles.card}>
      <div className={styles.head}>
        <AiMark />
        <input
          className={styles.title}
          value={title}
          aria-label="할 일 제목"
          onChange={(e) => setTitle(e.target.value)}
          onBlur={saveTitle}
          onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
        />
      </div>
      <div className={styles.row}>
        <AssigneeSelect members={members} value={g.assigneeId} onChange={(assigneeId) => onEdit({ assigneeId })} />
        <DueInput value={g.dueDate} onChange={(dueDate) => onEdit({ dueDate })} />
        <button type="button" className="btn small del" onClick={() => setAsking(true)}>
          삭제
        </button>
        <button
          type="button"
          className="btn small primary"
          onClick={() => {
            saveTitle() // 칸을 벗어나지 않고 바로 눌러도 고친 제목으로 확정
            onConfirm()
          }}
        >
          확정
        </button>
      </div>
      {asking && (
        <ConfirmSheet
          title="이 제안을 삭제할까요?"
          body={`'${g.title}' 제안을 삭제해요. 할 일로 등록되지 않아요.`}
          okLabel="삭제"
          danger
          onClose={({ ok }) => {
            setAsking(false)
            if (ok) onDismiss()
          }}
        />
      )}
    </article>
  )
}
