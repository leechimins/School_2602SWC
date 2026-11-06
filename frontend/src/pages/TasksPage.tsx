import { changeTaskStatus, getTeamTasks } from '../api/tasks.ts'
import EmptyState from '../components/EmptyState.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import TaskRow from '../components/TaskRow.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { PATHS } from '../lib/paths.ts'
import styles from './TasksPage.module.css'

// 할 일 탭: 팀 할 일. 상태 필터·사람별 묶음·담당자 지정·고치기는 #26에서 시안10 모양으로 채운다
export default function TasksPage() {
  const user = useCurrentUser()
  const res = useApi(() => getTeamTasks(user.roomId), [user.roomId, user.id])

  return (
    <Screen title="할 일">
      {res.status === 'error' && <RetryBox message={res.message} onRetry={res.reload} />}
      {res.status === 'ready' && (
        <section className="sec">
          {res.data.tasks.length === 0 ? (
            <EmptyState
              title="아직 할 일이 없어요"
              description="회의를 기록하면 에이전트가 할 일을 뽑아 제안해요."
              action={{ label: '일정으로 가기', to: PATHS.schedule }}
            />
          ) : (
            <ul className={styles.list}>
              {res.data.tasks.map((task) => (
                <TaskRow
                  key={task.id}
                  task={task}
                  onStatusChange={(t, status, reason) => changeTaskStatus(user.roomId, t.id, status, reason)}
                />
              ))}
            </ul>
          )}
        </section>
      )}
    </Screen>
  )
}
