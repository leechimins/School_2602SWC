import { useState } from 'react'
import { Link } from 'react-router-dom'
import { formatMD } from '../lib/date.ts'
import { withJosa } from '../lib/korean.ts'
import { pathTo } from '../lib/paths.ts'
import type { Member } from '../types/room.ts'
import type { Task, TaskInput } from '../types/task.ts'
import ConfirmSheet from './ConfirmSheet.tsx'
import { AssigneeSelect, DueInput } from './TaskFields.tsx'
import styles from './TaskEditor.module.css'

type Props = {
  task: Task
  members: Member[]
  onSave: (patch: Partial<TaskInput>) => void
  onDelete: () => void
  onClose: () => void
}

// 할 일 고치기(행을 길게 누르거나 우클릭): 제목 / 담당자 · 기한 / 출처 | 취소 · 삭제 · 수정
// 확정된 할 일은 누구나 고치고 지울 수 있다. 지우기는 한 번 더 묻는다.
export default function TaskEditor({ task, members, onSave, onDelete, onClose }: Props) {
  const [draft, setDraft] = useState<TaskInput>({ title: task.title, assigneeId: task.assigneeId, dueDate: task.dueDate })
  const [asking, setAsking] = useState(false)
  const set = (patch: Partial<TaskInput>) => setDraft({ ...draft, ...patch })

  const save = () => {
    onSave({ ...draft, title: draft.title.trim() || task.title })
    onClose()
  }

  return (
    <div className={styles.panel}>
      <input className="field" value={draft.title} aria-label="할 일 제목" onChange={(e) => set({ title: e.target.value })} />
      <div className={styles.fields}>
        <AssigneeSelect members={members} value={draft.assigneeId} onChange={(assigneeId) => set({ assigneeId })} />
        <DueInput value={draft.dueDate} onChange={(dueDate) => set({ dueDate })} />
      </div>
      <div className={styles.actions}>
        <span className="meta">
          출처{' '}
          {task.source ? (
            <Link to={pathTo.meeting(task.source.meetingId)}>
              {formatMD(task.source.heldOn)} {task.source.topic}
            </Link>
          ) : (
            '직접 추가'
          )}
        </span>
        <span className={styles.buttons}>
          <button type="button" className="btn small quiet" onClick={onClose}>
            취소
          </button>
          <button type="button" className="btn small del" onClick={() => setAsking(true)}>
            삭제
          </button>
          <button type="button" className="btn small primary" onClick={save}>
            수정
          </button>
        </span>
      </div>
      {asking && (
        <ConfirmSheet
          title="이 할 일을 삭제할까요?"
          body={`${withJosa(`'${task.title}'`, '을/를')} 할 일에서 삭제해요. ${task.assigneeName ? `${task.assigneeName}의 ` : ''}내 할 일에서도 사라져요.`}
          okLabel="삭제"
          danger
          onClose={({ ok }) => {
            setAsking(false)
            if (ok) onDelete()
          }}
        />
      )}
    </div>
  )
}
