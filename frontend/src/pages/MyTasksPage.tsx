import { useState } from 'react'
import { getRoom } from '../api/rooms.ts'
import { changeTaskStatus, dismissTask, editTask, getMyTasks } from '../api/tasks.ts'
import EmptyState from '../components/EmptyState.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import TaskEditor from '../components/TaskEditor.tsx'
import TaskRow from '../components/TaskRow.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { PATHS } from '../lib/paths.ts'
import type { Id } from '../types/common.ts'
import styles from './TasksPage.module.css'

// 내 할 일: 확정된 것만 기한 순. 상태는 행의 칩으로 바꾸고, 길게 누르면(우클릭도) 고치기 — 출처는 고치기 패널에 있다
export default function MyTasksPage() {
  const user = useCurrentUser()
  const res = useApi(() => getMyTasks(user.roomId), [user.roomId, user.id])
  const room = useApi(() => getRoom(user.roomId), [user.roomId, user.id])
  const members = room.status === 'ready' ? room.data.members : []
  const [editingId, setEditingId] = useState<Id | null>(null)

  return (
    <Screen title="내 할 일" backTo={PATHS.tasks}>
      {res.status === 'error' && <RetryBox message={res.message} onRetry={res.reload} />}
      {res.status === 'ready' &&
        (res.data.length === 0 ? (
          <section className="sec">
            <EmptyState
              title="맡은 할 일이 없어요"
              description="팀 할 일에서 담당자 없는 일을 맡거나, 회의록에서 제안을 확정하면 여기에 들어와요."
              action={{ label: '팀 할 일 보기', to: PATHS.tasks }}
            />
          </section>
        ) : (
          <>
            <p className={`meta ${styles.guide}`}>길게 누르거나 우클릭하면 고치기</p>
            <section className="sec">
              <ul className={styles.list}>
                {res.data.map((task) => (
                  <TaskRow
                    key={task.id}
                    task={task}
                    onStatusChange={(t, status, reason) => changeTaskStatus(user.roomId, t.id, status, reason)}
                    onEdit={task.canEdit ? (t) => setEditingId(t.id) : undefined}
                  >
                    {editingId === task.id && (
                      <TaskEditor
                        task={task}
                        members={members}
                        onSave={(patch) => editTask(user.roomId, task.id, patch)}
                        onDelete={() => dismissTask(user.roomId, task.id)}
                        onClose={() => setEditingId(null)}
                      />
                    )}
                  </TaskRow>
                ))}
              </ul>
            </section>
          </>
        ))}
    </Screen>
  )
}
