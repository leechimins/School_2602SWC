import { useState } from 'react'
import { formatMD } from '../lib/date.ts'
import { withJosa } from '../lib/korean.ts'
import type { UnneededTask } from '../types/meeting.ts'
import AiMark from './AiMark.tsx'
import Badge from './Badge.tsx'
import ConfirmSheet from './ConfirmSheet.tsx'
import styles from './SuggestionCard.module.css'

type Props = {
  item: UnneededTask
  onKeep: () => void
  onDelete: () => void
}

// 필요 없어 보이는 일(회의록): 회의에서 안 해도 된다고 한 확정된 할 일. 유지 | 삭제
// 지우기 전까지는 할 일 탭에 그대로 있다. 삭제하면 담당자의 내 할 일에서도 빠져 한 번 더 묻는다.
export default function UnneededCard({ item: { task, why, kept }, onKeep, onDelete }: Props) {
  const [asking, setAsking] = useState(false)
  const owner = task.assigneeName ?? '담당자 없음'

  if (kept) {
    return (
      <article className={`${styles.card} ${styles.plain}`}>
        <div className={styles.head}>
          <Badge>유지함</Badge>
          <span className="strong">{task.title}</span>
        </div>
        <p className="meta num">
          {owner}
          {task.dueDate && ` · ${formatMD(task.dueDate)}까지`}
        </p>
      </article>
    )
  }

  return (
    <article className={styles.card}>
      <div className={styles.head}>
        <AiMark />
        <span className="strong">{task.title}</span>
      </div>
      <p className="meta">
        {owner} 담당 · {why}
      </p>
      <div className={styles.act}>
        <button type="button" className="btn small quiet" onClick={onKeep}>
          유지
        </button>
        <button type="button" className="btn small danger" onClick={() => setAsking(true)}>
          삭제
        </button>
      </div>
      {asking && (
        <ConfirmSheet
          title="이 할 일을 삭제할까요?"
          body={`${withJosa(`'${task.title}'`, '을/를')} 할 일에서 삭제해요.${task.assigneeName ? ` ${task.assigneeName}의 내 할 일에서도 사라져요.` : ''}`}
          okLabel="삭제"
          danger
          onClose={({ ok }) => {
            setAsking(false)
            if (ok) onDelete()
          }}
        />
      )}
    </article>
  )
}
