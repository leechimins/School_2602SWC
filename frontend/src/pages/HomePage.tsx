import { Link } from 'react-router-dom'
import { getHome } from '../api/rooms.ts'
import { changeTaskStatus } from '../api/tasks.ts'
import Badge from '../components/Badge.tsx'
import EmptyState from '../components/EmptyState.tsx'
import Icon from '../components/Icon.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import TaskRow from '../components/TaskRow.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { formatDDay, formatDayLabel, formatRange, formatSlot } from '../lib/date.ts'
import { PATHS, pathTo } from '../lib/paths.ts'
import type { Home } from '../types/home.ts'
import styles from './HomePage.module.css'

// 홈: 지금 무엇을 봐야 하는지 한 화면에. 기간 카드는 #26에서 시안10 모양으로 채운다
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
          <NextMeeting home={home.data} />
          {home.data.canStartScheduling && (
            <Link to={PATHS.schedulingNew} className={`sec ${styles.newMeeting}`}>
              <b>+ 새 회의 잡기</b>
              <span className="meta">기간과 길이만 정하면 에이전트들이 시간을 조율해요</span>
            </Link>
          )}
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

// 다음 회의: 조율 중이면 조율 과정으로, 회의안이 나왔으면 조율 결과로 들어간다
function NextMeeting({ home }: { home: Home }) {
  const { coordinating: c, nextMeeting: m } = home
  if (c) {
    return (
      <section className="sec">
        <div className="row-between">
          <h2>다음 회의</h2>
          <Badge>조율 중</Badge>
        </div>
        <p className="strong">{c.topic}</p>
        <p className="meta num">{formatRange(c.windowStart, c.windowEnd)} 사이 · 에이전트끼리 시간을 맞추는 중</p>
        <Link to={pathTo.scheduling(c.id)} className="btn small block">
          조율 과정 보기
        </Link>
      </section>
    )
  }
  if (!m) {
    return (
      <section className="sec">
        <h2>다음 회의</h2>
        <p className="strong">아직 잡힌 회의가 없어요</p>
        <p className="meta">
          {home.canStartScheduling ? '마감 전에 필요할 때 언제든 잡아요.' : '팀장이 회의를 잡으면 알려 드려요.'}
        </p>
      </section>
    )
  }
  // 조율이 끝나면 바로 확정이라 사람이 응답할 것은 없다. proposed는 서버가 정리 중일 때만 잠깐 보인다
  const confirmed = m.status === 'confirmed'
  return (
    <section className="sec">
      <div className="row-between">
        <h2>다음 회의</h2>
        <Badge tone={confirmed ? 'ok' : 'plain'}>{confirmed ? '확정' : '정리 중'}</Badge>
      </div>
      <p className="strong">{m.topic}</p>
      <p className="meta num">
        {formatSlot(m.startAt, m.endAt)} · {m.mode}
      </p>
      <Link to={pathTo.proposal(m.id)} className="btn small block">
        조율 결과 보기
      </Link>
    </section>
  )
}
