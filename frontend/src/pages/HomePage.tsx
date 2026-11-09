import { Link } from 'react-router-dom'
import { getHome } from '../api/rooms.ts'
import { changeTaskStatus } from '../api/tasks.ts'
import Icon from '../components/Icon.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import TaskRow from '../components/TaskRow.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useClock } from '../hooks/useClock.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { dueGroup, formatDDay, formatMD, formatTime, periodOf, weekday } from '../lib/date.ts'
import { PATHS, pathTo } from '../lib/paths.ts'
import type { Home } from '../types/home.ts'
import styles from './HomePage.module.css'

const TODAY_MAX = 3 // 오늘 챙길 일: 기한 지남·오늘 중 최대 셋

// 홈(11/9 시안): 윗줄(방 이름 · 알림) → 인사(+ 달력 그림) → 마감 디데이 → 다음 회의 | 내 할 일 → 오늘 챙길 일.
// 할 일 전체는 할 일 탭, 새 회의 잡기는 회의 탭에 있다. 홈은 "지금 뭐가 있지?"만 답한다.
export default function HomePage() {
  const user = useCurrentUser()
  const home = useApi(() => getHome(user.roomId), [user.roomId, user.id])

  return (
    <Screen title="홈" bare>
      {home.status === 'error' && <RetryBox message={home.message} onRetry={home.reload} />}
      {home.status === 'ready' && <HomeBody home={home.data} name={user.name} />}
    </Screen>
  )
}

function HomeBody({ home, name }: { home: Home; name: string }) {
  const { total, passed, left } = periodOf(home.startDate, home.dueDate, home.today)
  const percent = Math.round((passed / total) * 100)

  return (
    <>
      <div className={styles.topBar}>
        <Link to={PATHS.team} className={styles.roomPill}>
          <Icon name="person" small />
          <span>{home.roomName}</span>
        </Link>
        <Link to={PATHS.notifications} className={styles.bell} aria-label={`알림, 안 읽은 것 ${home.unreadCount}개`}>
          <Icon name="bell" />
          {home.unreadCount > 0 && <i className={styles.dot} aria-hidden="true" />}
        </Link>
      </div>

      <div className={styles.greet}>
        <h1 className={styles.hello}>
          {name ? `${name}님,` : '안녕하세요,'}
          <br />
          오늘도 프로젝트를
          <br />
          <b>TTAK</b> 맞춰가요!
        </h1>
        <img className={styles.peek} src="/splash/calendar.webp" alt="" aria-hidden="true" />
      </div>

      <section className={`sec ${styles.dday}`}>
        <div>
          <p className={styles.ddayLabel}>프로젝트 마감까지</p>
          <b className={`${styles.ddayNum} num`}>{formatDDay(left)}</b>
        </div>
        <div className={styles.ddayRight}>
          <span className={styles.bar} role="img" aria-label={`전체 ${total}일 중 ${passed}일 지남`}>
            <i style={{ width: `${percent}%` }} />
          </span>
          <span className="meta num">기간 {percent}% 지남</span>
        </div>
      </section>

      <div className={styles.tiles}>
        <NextMeetingTile home={home} />
        <Link to={PATHS.myTasks} className={styles.tile}>
          <span className={styles.tileIcon} data-tint="violet" aria-hidden="true">
            <Icon name="check" small />
          </span>
          <b className={styles.tileTitle}>내 할 일</b>
          <span className={`${styles.tileSub} num`}>{home.myTasks.filter((t) => t.status !== '완료').length}개 남음</span>
          <span className={styles.chev} aria-hidden="true">
            <Icon name="back" small />
          </span>
        </Link>
      </div>

      <TodayTasks home={home} />
    </>
  )
}

// 다음 회의 타일: 조율 중이면 조율 과정으로, 회의안이 나왔으면 조율 결과로, 없으면 회의 탭으로
function NextMeetingTile({ home }: { home: Home }) {
  const { coordinating: c, nextMeeting: m } = home
  const to = c ? pathTo.scheduling(c.id) : m ? pathTo.proposal(m.id) : PATHS.schedule
  const topic = c?.topic ?? m?.topic ?? '잡힌 회의 없음'
  const when = c
    ? '시간 맞추는 중'
    : m
      ? `${formatMD(m.startAt).replace('/', '.')} (${weekday(m.startAt)}) ${formatTime(m.startAt)}`
      : '회의 탭에서 잡아요'

  return (
    <Link to={to} className={styles.tile}>
      <span className={styles.tileIcon} aria-hidden="true">
        <Icon name="calendar" small />
      </span>
      <b className={styles.tileTitle}>다음 회의</b>
      <span className={styles.tileSub}>{topic}</span>
      <span className={`${styles.tileSub} num`}>{when}</span>
      <span className={styles.chev} aria-hidden="true">
        <Icon name="back" small />
      </span>
    </Link>
  )
}

// 오늘 챙길 일: 기한 지남 → 오늘 순으로 최대 셋. 없으면 카드째 숨긴다
function TodayTasks({ home }: { home: Home }) {
  const user = useCurrentUser()
  const now = useClock()
  const open = home.myTasks.filter((t) => t.status !== '완료')
  const late = open.filter((t) => dueGroup(t.dueDate, now) === '기한 지남')
  const today = open.filter((t) => dueGroup(t.dueDate, now) === '오늘')
  const picks = [...late, ...today].slice(0, TODAY_MAX)
  if (picks.length === 0) return null

  return (
    <section className="sec">
      <div className={styles.cardHead}>
        <h2>오늘 챙길 일</h2>
        <Link to={PATHS.myTasks} className={styles.more}>
          전체 보기 ›
        </Link>
      </div>
      <ul className={styles.list}>
        {picks.map((task) => (
          <TaskRow
            key={task.id}
            task={task}
            onStatusChange={(t, status, reason) => changeTaskStatus(user.roomId, t.id, status, reason)}
          />
        ))}
      </ul>
    </section>
  )
}
