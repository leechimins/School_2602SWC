import { Link } from 'react-router-dom'
import { getHome } from '../api/rooms.ts'
import { getSchedule } from '../api/scheduling.ts'
import { changeTaskStatus } from '../api/tasks.ts'
import BrandHero from '../components/BrandHero.tsx'
import Icon from '../components/Icon.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import TaskRow from '../components/TaskRow.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { formatDDay, formatMD, formatTime, formatYearMonth, isSameDay, periodOf, weekday, weekOf } from '../lib/date.ts'
import { PATHS, pathTo } from '../lib/paths.ts'
import type { Home } from '../types/home.ts'
import type { MeetingBrief } from '../types/meeting.ts'
import type { Task } from '../types/task.ts'
import styles from './HomePage.module.css'

const TASK_MAX = 4 // 오늘 할 일: 내 할 일 중 넷

// 홈(11/9 시안): 보라 머리(로고 · 알림 · 캐릭터) → 주간 달력(다음 회의 · 마감 디데이) → 오늘 할 일 → 마감 디데이.
// 하단 탭과 다른 화면은 그대로다. 홈은 "이번 주에 뭐가 있지?"만 답한다.
export default function HomePage() {
  const user = useCurrentUser()
  const home = useApi(() => getHome(user.roomId), [user.roomId, user.id])
  // 회의 있는 날 점. 실패해도 점만 빠지고 홈은 그대로 그린다
  const schedule = useApi(() => getSchedule(user.roomId), [user.roomId, user.id])
  const meetings = schedule.status === 'ready' ? schedule.data.upcoming : []

  return (
    <Screen title="홈" bare>
      {home.status === 'error' && <RetryBox message={home.message} onRetry={home.reload} />}
      {home.status === 'ready' && <HomeBody home={home.data} meetings={meetings} />}
    </Screen>
  )
}

function HomeBody({ home, meetings }: { home: Home; meetings: MeetingBrief[] }) {
  return (
    <>
      <BrandHero unread={home.unreadCount}>
        <WeekCard home={home} meetings={meetings} />
        <TodayTasks tasks={home.myTasks} />
        <DeadlineCard home={home} />
      </BrandHero>
    </>
  )
}

// 주간 달력: 이번 주 월~일 + 회의 있는 날(보라 점) · 할 일 기한(회색 점) · 프로젝트 마감(핑크 꼬리표).
// 아래 한 줄에 다음 회의와 마감 디데이
function WeekCard({ home, meetings }: { home: Home; meetings: MeetingBrief[] }) {
  const days = weekOf(home.today)
  const { left } = periodOf(home.startDate, home.dueDate, home.today)
  const { coordinating: c, nextMeeting: m } = home
  const to = c ? pathTo.scheduling(c.id) : m ? pathTo.proposal(m.id) : PATHS.schedule
  const next = c
    ? `시간 맞추는 중 · ${c.topic}`
    : m
      ? `${formatMD(m.startAt)}(${weekday(m.startAt)}) ${formatTime(m.startAt)} ${m.topic}`
      : '잡힌 회의 없음'

  return (
    <section className={`sec ${styles.week}`}>
      <div className={styles.weekHead}>
        <span className={styles.month}>
          <Icon name="calendar" />
          {formatYearMonth(home.today)}
        </span>
        <Link to={PATHS.schedule} className={styles.pill}>
          <Icon name="calendar" small /> 일정 보기
        </Link>
      </div>

      <ol className={styles.days}>
        {days.map((day) => {
          const iso = day.format('YYYY-MM-DD')
          const isToday = isSameDay(day, home.today)
          const hasMeeting = meetings.some((mt) => isSameDay(mt.startAt, day))
          const hasDue = home.myTasks.some((t) => t.dueDate === iso && t.status !== '완료')
          const isDeadline = isSameDay(home.dueDate, day)
          return (
            <li key={iso} className={styles.day} data-dow={day.day()} data-today={isToday}>
              {isDeadline && <span className={styles.deadlineTag}>마감</span>}
              <span className={styles.dow}>{weekday(day)}</span>
              <b className={`${styles.date} num`}>{day.date()}</b>
              <span className={styles.marks} aria-hidden="true">
                {hasMeeting && <i className={styles.meetDot} />}
                {hasDue && <i className={styles.dueDot} />}
              </span>
            </li>
          )
        })}
      </ol>

      <div className={styles.weekFoot}>
        <Link to={to} className={styles.next}>
          <span className={styles.nextLabel}>다음 회의</span>
          <span className={`${styles.nextText} num`}>{next}</span>
        </Link>
        <span className={`${styles.ddayChip} num`}>마감 {formatDDay(left)}</span>
      </div>
    </section>
  )
}

// 오늘 할 일: 내 할 일 전부 중 넷. 끝낸 일을 위로, 그다음 남은 일을 기한 순으로. 알약은 완료/전체
function TodayTasks({ tasks }: { tasks: Task[] }) {
  const user = useCurrentUser()
  const done = tasks.filter((t) => t.status === '완료')
  const open = tasks.filter((t) => t.status !== '완료') // 서버가 기한 순으로 준다
  const picks = [...done, ...open].slice(0, TASK_MAX)

  return (
    <section className="sec">
      <div className={styles.cardHead}>
        <h2>
          오늘 할 일 <span className={`${styles.count} num`}>{done.length}/{tasks.length}</span>
        </h2>
        <Link to={PATHS.myTasks} className={styles.more}>
          전체 보기 ›
        </Link>
      </div>
      {picks.length === 0 ? (
        <p className="meta">아직 할 일이 없어요</p>
      ) : (
        <ul className={styles.list}>
          {picks.map((task) => (
            <TaskRow
              key={task.id}
              task={task}
              onStatusChange={(t, status, reason) => changeTaskStatus(user.roomId, t.id, status, reason)}
            />
          ))}
        </ul>
      )}
    </section>
  )
}

// 마감 디데이(시안의 "이번 주 진행률" 자리): 디데이 + 기간 막대 + 달력 그림
function DeadlineCard({ home }: { home: Home }) {
  const { total, passed, left } = periodOf(home.startDate, home.dueDate, home.today)
  const percent = Math.round((passed / total) * 100)
  return (
    <section className={`sec ${styles.deadline}`}>
      <div className={styles.deadlineText}>
        <p className={styles.deadlineLabel}>프로젝트 마감까지</p>
        <b className={`${styles.ddayNum} num`}>{formatDDay(left)}</b>
      </div>
      <div className={styles.deadlineBar}>
        <span className={styles.bar} role="img" aria-label={`전체 ${total}일 중 ${passed}일 지남`}>
          <i style={{ width: `${percent}%` }} />
        </span>
        <span className="meta num">기간 {percent}% 지남</span>
      </div>
      <img className={styles.cal} src="/splash/calendar.webp" alt="" aria-hidden="true" />
    </section>
  )
}
