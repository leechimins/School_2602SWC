import { useState, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { messageOf } from '../api/client.ts'
import { getHome, setAutoSchedule } from '../api/rooms.ts'
import { changeTaskStatus } from '../api/tasks.ts'
import Badge from '../components/Badge.tsx'
import DateBlock from '../components/DateBlock.tsx'
import EmptyState from '../components/EmptyState.tsx'
import Icon from '../components/Icon.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import PeriodCard from '../components/PeriodCard.tsx'
import TaskRow from '../components/TaskRow.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useClock } from '../hooks/useClock.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import {
  dueGroup,
  formatCountdown,
  formatDuration,
  formatStamp,
  formatRange,
  formatTimeRange,
  minutesBetween,
  type DueGroup,
} from '../lib/date.ts'
import { answerLine } from '../lib/meeting.ts'
import { PATHS, pathTo } from '../lib/paths.ts'
import type { Home, MeetingSuggestion } from '../types/home.ts'
import type { Task } from '../types/task.ts'
import styles from './HomePage.module.css'

// 홈: 지금 무엇을 봐야 하는지 한 화면에 — 기간(마감 디데이) · 다음 회의 · 새 회의 잡기(팀장) · 내 할 일.
// "먼저 챙길 것"은 홈에 따로 두지 않고 종의 숫자와 할 일 옆 늦음·막힘 뱃지로 알린다
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
  // 보라 띠 머리: 로고 | 반투명 흰 알약에 팀 이름 | 종. 솜솜이 한 장이 기간 카드 위에 손을 걸친다
  const hero = (
    <header className={styles.hero}>
      <div className={styles.heroText}>
        <img className={styles.logo} src="/brand/logo-white.webp" alt="TTAK" />
        <h1 className={styles.title}>
          <Icon name="team" small />
          <span>{title}</span>
        </h1>
      </div>
      {bell}
    </header>
  )

  return (
    <Screen title={title} hero={hero}>
      {home.status === 'error' && <RetryBox message={home.message} onRetry={home.reload} />}
      {home.status === 'ready' && (
        <>
          <div className={styles.lift}>
            <img className={styles.somsom} src="/brand/somsom-face.webp" alt="" />
            <PeriodCard startDate={home.data.startDate} dueDate={home.data.dueDate} today={home.data.today} />
          </div>
          {home.data.suggestion && <Suggestion s={home.data.suggestion} roomId={user.roomId} today={home.data.today} />}
          <AgentPanel home={home.data} roomId={user.roomId} onChanged={home.reload} />
          <NextMeeting home={home.data} />
          {home.data.canStartScheduling && (
            <Link to={PATHS.schedulingNew} className={`sec ${styles.newMeeting}`}>
              <span className={styles.newIcon}>
                <Icon name="calendar" />
              </span>
              <b>새 회의 잡기</b>
              <span className={styles.plus} aria-hidden="true">
                +
              </span>
            </Link>
          )}
          <MyTasks tasks={home.data.myTasks} />
        </>
      )}
    </Screen>
  )
}

// 내 할 일 묶음 순서와 이름표 점 색. 기한 지남만 빨강, 오늘·내일은 포인트색
const GROUPS: { label: DueGroup; color: string }[] = [
  { label: '기한 지남', color: 'var(--danger)' },
  { label: '오늘', color: 'var(--point)' },
  { label: '내일', color: 'var(--point)' },
  { label: '그 이후', color: 'var(--text)' },
  { label: '기한 없음', color: 'var(--check-idle)' },
]

// 내 할 일: 기한으로 묶고(기한 지남 → 오늘 → 내일 → 그 이후), 끝낸 일은 맨 아래 "완료"
function MyTasks({ tasks }: { tasks: Task[] }) {
  const user = useCurrentUser()
  const now = useClock()
  const open = tasks.filter((t) => t.status !== '완료')
  const done = tasks.filter((t) => t.status === '완료')
  const groups = [
    ...GROUPS.map((g) => ({ ...g, tasks: open.filter((t) => dueGroup(t.dueDate, now) === g.label) })),
    { label: '완료', color: 'var(--check-idle)', tasks: done },
  ].filter((g) => g.tasks.length > 0)
  const row = (task: Task) => (
    <TaskRow
      key={task.id}
      task={task}
      onStatusChange={(t, status, reason) => changeTaskStatus(user.roomId, t.id, status, reason)}
    />
  )

  return (
    <section className="sec">
      <div className="row-between">
        <h2>내 할 일</h2>
        {tasks.length > 0 && (
          <Link to={PATHS.tasks} className="btn small">
            팀 할 일 보기
          </Link>
        )}
      </div>
      {tasks.length === 0 ? (
        <EmptyState
          title="아직 할 일이 없어요"
          action={{ label: '일정으로 가기', to: PATHS.schedule }}
        />
      ) : (
        <>
          {open.length === 0 && <p className="meta">남은 할 일이 없어요.</p>}
          {groups.map((g) => (
            <div key={g.label}>
              <span className="cat" style={{ '--mc': g.color } as CSSProperties}>
                {g.label} <span className="n num">{g.tasks.length}</span>
              </span>
              <ul className={styles.list}>{g.tasks.map(row)}</ul>
            </div>
          ))}
        </>
      )}
    </section>
  )
}

// 다음 회의: 조율 중이면 조율 과정으로, 회의안이 나왔으면 조율 결과로 들어간다.
// 서버는 아직 안 끝난 회의를 주므로, 시작 시각이 지났으면(진행 중) 카운트다운 대신 회의록으로 보낸다.
// "지금 회의 기록하기"로 만든 회의도 늘 시작한 뒤라 여기로 와서, 없는 조율 결과로 가지 않는다
function NextMeeting({ home }: { home: Home }) {
  const { coordinating: c, nextMeeting: m } = home
  const now = useClock()
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
  const started = !now.isBefore(m.startAt)
  const confirmed = m.status === 'confirmed'
  const waiting = !started && !confirmed && m.myState === '대기'
  const answers = answerLine(m, home.joinedCount)
  return (
    <section className="sec">
      <div className="row-between">
        <h2>다음 회의</h2>
        {started ? <Badge tone="here">진행 중</Badge> : <Badge tone={confirmed ? 'ok' : 'warn'}>{confirmed ? '확정' : '확정 대기'}</Badge>}
      </div>
      <div className={styles.meet}>
        <DateBlock at={m.startAt} />
        <div className={styles.meetBody}>
          <p className="strong">{m.topic}</p>
          <p className="meta num">
            {formatTimeRange(m.startAt, m.endAt)} · {m.mode} · {formatDuration(minutesBetween(m.startAt, m.endAt))}
          </p>
          {started ? (
            <p className={styles.tick}>회의 진행 중</p>
          ) : (
            <p className={styles.tick}>
              시작까지 <span className="num">{formatCountdown(m.startAt, now)}</span>
            </p>
          )}
        </div>
      </div>
      <div className={`row-between ${styles.meetFoot}`}>
        <span className="meta">{started ? '끝나면 회의록에 기록해요' : answers}</span>
        {started ? (
          <Link to={pathTo.meeting(m.id)} className="btn small primary">
            회의록 보기
          </Link>
        ) : (
          <Link to={pathTo.proposal(m.id)} className={`btn small ${waiting ? 'primary' : ''}`}>
            조율 결과 보기
          </Link>
        )}
      </div>
    </section>
  )
}

// "나중에"를 누르면 같은 이유로는 그날 다시 띄우지 않는다. 서버에 쓰지 않는다(브라우저마다 따로)
const snoozeKey = (roomId: string, kind: string) => `ttak:suggest:${roomId}:${kind}`
function snoozedToday(key: string, today: string): boolean {
  try {
    return localStorage.getItem(key) === today
  } catch {
    return false
  }
}

// 에이전트가 먼저 꺼내는 제안: 왜 지금인지 한 줄 + 주제·기간을 채운 조율 화면으로. 시작은 팀장이 누른다
function Suggestion({ s, roomId, today }: { s: MeetingSuggestion; roomId: string; today: string }) {
  const key = snoozeKey(roomId, s.kind)
  const [hidden, setHidden] = useState(() => snoozedToday(key, today))
  if (hidden) return null
  const later = () => {
    try {
      localStorage.setItem(key, today)
    } catch {
      // 저장이 안 되면 이번 화면에서만 숨긴다
    }
    setHidden(true)
  }
  const query = new URLSearchParams({ topic: s.topic, from: s.windowStart, to: s.windowEnd })
  return (
    <section className={`sec ${styles.suggest}`} aria-label="에이전트 제안">
      <p className={styles.suggestWho}>
        <img src="/brand/somsom-face.webp" alt="" />
        에이전트 제안
      </p>
      <p className="strong">{s.reason}</p>
      <p className="meta num">
        {s.topic} · {formatRange(s.windowStart, s.windowEnd)} 사이
      </p>
      <div className={styles.suggestActions}>
        <button type="button" className="btn small" onClick={later}>
          나중에
        </button>
        <Link to={`${PATHS.schedulingNew}?${query}`} className="btn small primary">
          조율 시작하기
        </Link>
      </div>
    </section>
  )
}

// 에이전트 칸: 팀장이 조율 시작을 맡기는 스위치와, 에이전트가 혼자 한 일 최근 몇 줄.
// 켜면 홈을 다시 불러 그 자리에서 조건을 본다 — 이유가 있으면 바로 "조율 중"이 뜬다
function AgentPanel({ home, roomId, onChanged }: { home: Home; roomId: string; onChanged: () => void }) {
  const [on, setOn] = useState(home.autoSchedule)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const toggle = async (next: boolean) => {
    setOn(next)
    setBusy(true)
    setError(null)
    try {
      await setAutoSchedule(roomId, next)
      onChanged()
    } catch (e) {
      setOn(!next)
      setError(messageOf(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="sec" aria-label="에이전트">
      <div className="row-between">
        <h2>에이전트가 한 일</h2>
        <Link to={PATHS.activity} className="btn small">
          전체 보기
        </Link>
      </div>
      {home.canStartScheduling ? (
        <label className={styles.auto}>
          <input type="checkbox" checked={on} disabled={busy} onChange={(e) => toggle(e.target.checked)} />
          <span>
            <span className="strong">회의가 필요하면 조율까지 맡기기</span>
            <span className="meta">이유가 생기면 에이전트가 먼저 조율을 시작해요. 확정은 모두의 수락으로 해요.</span>
          </span>
        </label>
      ) : (
        home.autoSchedule && <p className="meta">팀장이 조율 시작을 에이전트에게 맡겨 뒀어요.</p>
      )}
      {error && <p className="meta" role="alert">{error}</p>}
      {home.agentLog.length === 0 ? (
        <p className="meta">아직 한 일이 없어요.</p>
      ) : (
        <ul className={styles.log}>
          {home.agentLog.map((a) => (
            <li key={a.id}>
              <div>
                <p className="strong">{a.what}</p>
                {a.why && <p className="meta">{a.why}</p>}
              </div>
              <span className="meta num">{formatStamp(a.at)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
