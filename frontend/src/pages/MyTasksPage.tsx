import { Link } from 'react-router-dom'
import { changeTaskStatus, getMyTasks } from '../api/tasks.ts'
import EmptyState from '../components/EmptyState.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import TaskRow from '../components/TaskRow.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { formatMD } from '../lib/date.ts'
import { PATHS, pathTo } from '../lib/paths.ts'
import type { Task } from '../types/task.ts'
import styles from './TasksPage.module.css'

// 내 할 일: 확정된 것만 기한 순, 줄마다 어느 회의에서 나왔는지(출처). 상태는 행의 칩으로 바꾼다
export default function MyTasksPage() {
  const user = useCurrentUser()
  const res = useApi(() => getMyTasks(user.roomId), [user.roomId, user.id])

  return (
    <Screen title="내 할 일" backTo={PATHS.tasks}>
      {res.status === 'error' && <RetryBox message={res.message} onRetry={res.reload} />}
      {res.status === 'ready' && (
        <section className="sec">
          {res.data.length === 0 ? (
            <EmptyState
              title="맡은 할 일이 없어요"
              description="팀 할 일에서 담당자 없는 일을 맡거나, 회의록에서 제안을 확정하면 여기에 들어와요."
              action={{ label: '팀 할 일 보기', to: PATHS.tasks }}
            />
          ) : (
            <ul className={styles.list}>
              {res.data.map((task) => (
                <TaskRow
                  key={task.id}
                  task={task}
                  onStatusChange={(t, status, reason) => changeTaskStatus(user.roomId, t.id, status, reason)}
                >
                  <Source task={task} />
                </TaskRow>
              ))}
            </ul>
          )}
        </section>
      )}
    </Screen>
  )
}

function Source({ task }: { task: Task }) {
  return (
    <p className={`meta ${styles.source}`}>
      {task.source ? (
        <Link to={pathTo.meeting(task.source.meetingId)}>
          {formatMD(task.source.heldOn)} {task.source.topic}
        </Link>
      ) : (
        '직접 추가'
      )}
      {task.blockedReason && ` · 막힌 이유 "${task.blockedReason}"`}
    </p>
  )
}
