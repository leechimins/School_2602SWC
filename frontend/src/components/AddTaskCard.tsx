import { useState } from 'react'
import type { Member } from '../types/room.ts'
import type { TaskInput } from '../types/task.ts'
import Badge from './Badge.tsx'
import styles from './SuggestionCard.module.css'
import { AssigneeSelect, DueInput } from './TaskFields.tsx'

type Props = {
  label: string // 닫혀 있을 때 버튼 글자: "+ 직접 추가" · "+ 할 일 추가"
  members: Member[]
  /** 추가. 실패하면 던져서 카드가 열린 채로 남는다 */
  onAdd: (input: TaskInput) => Promise<void>
}

const EMPTY: TaskInput = { title: '', assigneeId: null, dueDate: null }

// 할 일 직접 추가: AI 없이 도는 길이라 늘 쓸 수 있다. 제안을 거치지 않고 바로 확정된 할 일이 된다.
// 제안 카드와 같은 두 줄 모양이지만 흰 카드라 "AI 제안"이 아님이 보인다.
export default function AddTaskCard({ label, members, onAdd }: Props) {
  const [draft, setDraft] = useState<TaskInput | null>(null)
  const [error, setError] = useState('')

  if (!draft) {
    return (
      <button type="button" className={`btn small ${styles.open}`} onClick={() => setDraft(EMPTY)}>
        {label}
      </button>
    )
  }

  const set = (patch: Partial<TaskInput>) => setDraft({ ...draft, ...patch })
  const add = async () => {
    if (!draft.title.trim()) return setError('할 일 제목을 적어 주세요')
    try {
      await onAdd({ ...draft, title: draft.title.trim() })
      setDraft(null)
      setError('')
    } catch {
      setError('잠시 후 다시 해 주세요.')
    }
  }

  return (
    <article className={`${styles.card} ${styles.plain}`}>
      <div className={styles.head}>
        <Badge>직접 추가</Badge>
        <input
          className={styles.title}
          value={draft.title}
          placeholder="할 일 제목"
          aria-label="할 일 제목"
          autoFocus
          onChange={(e) => set({ title: e.target.value })}
          onKeyDown={(e) => e.key === 'Enter' && add()}
        />
      </div>
      <div className={styles.row}>
        <AssigneeSelect members={members} value={draft.assigneeId} onChange={(assigneeId) => set({ assigneeId })} />
        <DueInput value={draft.dueDate} onChange={(dueDate) => set({ dueDate })} />
        <button type="button" className="btn small quiet" onClick={() => setDraft(null)}>
          취소
        </button>
        <button type="button" className="btn small primary" onClick={add}>
          추가
        </button>
      </div>
      {error && (
        <p className="meta" role="alert">
          {error}
        </p>
      )}
    </article>
  )
}
