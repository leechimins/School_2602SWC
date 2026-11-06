import { Link } from 'react-router-dom'
import { getHome } from '../api/rooms.ts'
import { changeTaskStatus } from '../api/tasks.ts'
import EmptyState from '../components/EmptyState.tsx'
import Icon from '../components/Icon.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import TaskRow from '../components/TaskRow.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { formatDDay, formatDayLabel } from '../lib/date.ts'
import { PATHS } from '../lib/paths.ts'
import styles from './HomePage.module.css'

// 홈: 지금 무엇을 봐야 하는지 한 화면에. 기간 카드·다음 회의는 #26에서 시안10 모양으로 채운다
export default function HomePage() {
  const user = useCurrentUser()
  const home = useApi(() => getHome(user.roomId), [user.roomId, user.id])

  const unread = home.status === 'ready' ? home.data.unreadCount : 0
  const bell = (
    <Link to={PATHS.notifications} className="icon-btn" aria-label={`알림, 안 읽은 것 ${unread}개`}>
      <Icon name="bell" />
      {unread > 0 && <span className={`${styles.count} num`}>{unread}</span>}
    </Link>
  )
  const title = home.status === 'ready' ? home.data.roomName : '홈'

  return (
    <Screen title={title} aux={bell}>
      {home.status === 'error' && <RetryBox message={home.message} onRetry={home.reload} />}
      {home.status === 'ready' && (
        <>
          <section className="sec">
            <span className="meta">마감까지</span>
            <b className={`${styles.dday} num`}>{formatDDay(home.data.dDay)}</b>
            <span className="meta">오늘 {formatDayLabel(home.data.today)}</span>
          </section>
          <section className="sec">
            <h2>내 할 일</h2>
            {home.data.myTasks.length === 0 ? (
              <EmptyState title="아직 할 일이 없어요" action={{ label: '일정으로 가기', to: PATHS.schedule }} />
            ) : (
              <ul className={styles.list}>
                {home.data.myTasks.map((task) => (
                  <TaskRow
                    key={task.id}
                    task={task}
                    onStatusChange={(t, status, reason) => changeTaskStatus(user.roomId, t.id, status, reason)}
                  />
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </Screen>
  )
}
