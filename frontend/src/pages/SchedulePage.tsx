import { useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { messageOf } from '../api/client.ts'
import { canRecordLive, createMeeting } from '../api/records.ts'
import { getRoom } from '../api/rooms.ts'
import { getSchedule } from '../api/scheduling.ts'
import AiMark from '../components/AiMark.tsx'
import Badge from '../components/Badge.tsx'
import ConfirmSheet from '../components/ConfirmSheet.tsx'
import Icon, { type IconName } from '../components/Icon.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useClock } from '../hooks/useClock.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { formatDuration, formatMD, formatRange, formatTimeRange, isSameDay, minutesBetween, weekday } from '../lib/date.ts'
import { answerLine } from '../lib/meeting.ts'
import { PATHS, pathTo } from '../lib/paths.ts'
import type { MeetingBrief, Schedule } from '../types/meeting.ts'
import styles from './SchedulePage.module.css'

/** 11.03 (월) */
const dayText = (at: string) => `${formatMD(at).replace('/', '.')} (${weekday(at)})`

// 회의 탭(11/9 시안): 새 회의 조율하기(팀장) → 진행 중인 조율 → 확정된 회의 → 지난 회의(회의록).
// 지금 회의 받아적기는 지난 회의 제목 오른쪽 마이크 버튼으로 연다.
export default function SchedulePage() {
  const user = useCurrentUser()
  const res = useApi(() => getSchedule(user.roomId), [user.roomId, user.id])
  const room = useApi(() => getRoom(user.roomId), [user.roomId, user.id])
  const canStart = room.status === 'ready' && room.data.canStartScheduling

  return (
    <Screen title="회의" band={{ sub: '팀의 일정을 AI가 딱 맞게 조율해요.' }}>
      {canStart && (
        <Link to={PATHS.schedulingNew} className={styles.newBtn}>
          <Icon name="plus" /> 새 회의 조율하기
          <span className={styles.spark} aria-hidden="true">
            ✦
          </span>
        </Link>
      )}
      {res.status === 'error' && <RetryBox message={res.message} onRetry={res.reload} />}
      {res.status === 'ready' && <ScheduleBody schedule={res.data} total={room.status === 'ready' ? room.data.joinedCount : null} />}
    </Screen>
  )
}

// 섹션 제목(카드 밖): 아이콘 + 제목 (+ 오른쪽)
function SecHead({ icon, title, right }: { icon: IconName; title: string; right?: ReactNode }) {
  return (
    <div className={styles.secHead}>
      <span className={styles.secIcon} aria-hidden="true">
        <Icon name={icon} small />
      </span>
      <h2>{title}</h2>
      {right && <span className={styles.secRight}>{right}</span>}
    </div>
  )
}

function ScheduleBody({ schedule, total }: { schedule: Schedule; total: number | null }) {
  const now = useClock()
  const { coordinating, upcoming, past } = schedule
  // 오늘 잡힌 확정 회의가 있으면 그 줄에 "기록 시작"이 붙는다
  const today = upcoming.find((m) => m.status === 'confirmed' && isSameDay(m.startAt, now))

  return (
    <>
      {coordinating.length > 0 && (
        <>
          <SecHead icon="progress" title="진행 중인 조율" />
          {coordinating.map((c) => (
            <Link key={c.id} to={pathTo.scheduling(c.id)} className={`sec ${styles.card}`}>
              <span className={styles.spin} aria-hidden="true" />
              <span className={styles.body}>
                <b className={styles.topic}>{c.topic}</b>
                <span className="meta num">{formatRange(c.windowStart, c.windowEnd)} · 가능 시간 조율 중…</span>
              </span>
              <span className={styles.chev} aria-hidden="true">
                <Icon name="back" small />
              </span>
            </Link>
          ))}
        </>
      )}

      <SecHead icon="check" title="확정된 회의" />
      {upcoming.length === 0 ? (
        <p className={`meta ${styles.none}`}>잡힌 회의가 없어요</p>
      ) : (
        upcoming.map((m) => <UpcomingCard key={m.id} meeting={m} isToday={m.id === today?.id} total={total} />)
      )}

      <SecHead icon="tasks" title="지난 회의 · 회의록" right={<RecordNow todayMeeting={today ?? null} />} />
      {past.length === 0 ? (
        <p className={`meta ${styles.none}`}>아직 지난 회의가 없어요</p>
      ) : (
        past.map((m) => (
          <Link key={m.id} to={pathTo.meeting(m.id)} className={`sec ${styles.card}`}>
            <span className={`${styles.calIcon} ${styles.muted}`} aria-hidden="true">
              <Icon name="calendar" />
            </span>
            <span className={styles.body}>
              <b className={styles.topic}>{m.topic}</b>
              <span className="meta num">
                {dayText(m.startAt)} · {formatDuration(minutesBetween(m.startAt, m.endAt))} · {m.mode}
              </span>
            </span>
            {m.suggestionCount > 0 && <AiMark label={`제안 ${m.suggestionCount}개`} />}
            <span className={styles.chev} aria-hidden="true">
              <Icon name="back" small />
            </span>
          </Link>
        ))
      )}
    </>
  )
}

// 확정된 회의 카드: 누르면 조율 결과로. 오늘 회의면 오른쪽에 기록 시작
function UpcomingCard({ meeting: m, isToday, total }: { meeting: MeetingBrief; isToday: boolean; total: number | null }) {
  const confirmed = m.status === 'confirmed'
  return (
    <div className={`sec ${styles.card}`}>
      <Link to={pathTo.proposal(m.id)} className={styles.main}>
        <span className={styles.calIcon} aria-hidden="true">
          <Icon name="calendar" />
        </span>
        <span className={styles.body}>
          <b className={styles.topic}>
            {m.topic} {!confirmed && <Badge tone="warn">확정 대기</Badge>}
          </b>
          <span className="meta num">
            {dayText(m.startAt)} {formatTimeRange(m.startAt, m.endAt).replace('–', ' – ')} · {m.mode}
          </span>
          {!confirmed && <span className="meta">{answerLine(m, total)}</span>}
        </span>
      </Link>
      {isToday ? (
        <Link to={pathTo.record(m.id)} className="btn small primary">
          기록 시작
        </Link>
      ) : (
        <span className={styles.chev} aria-hidden="true">
          <Icon name="back" small />
        </span>
      )}
    </div>
  )
}

// 지금 회의 받아적기(실서버는 기록하기): 오늘 회의가 있으면 거기에 붙고, 없으면 주제 한 줄(비워도 됨)만 받고 바로 연다
function RecordNow({ todayMeeting }: { todayMeeting: MeetingBrief | null }) {
  const user = useCurrentUser()
  const navigate = useNavigate()
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState('')
  // 실서버는 받아적기가 없어 직접 쓰기만 연다(api/records.ts canRecordLive). 문구도 그에 맞춘다
  const label = canRecordLive() ? '지금 받아적기' : '지금 기록하기'

  const open = async (topic: string) => {
    try {
      const id = await createMeeting(user.roomId, { meetingId: null, topic: topic || null, mode: '대면' })
      navigate(pathTo.record(id))
    } catch (e) {
      setError(messageOf(e))
    }
  }

  return (
    <>
      <button
        type="button"
        className={styles.recBtn}
        onClick={() => (todayMeeting ? navigate(pathTo.record(todayMeeting.id)) : setAsking(true))}
      >
        <Icon name="mic" small /> {label}
      </button>
      {error && (
        <span className={`meta ${styles.error}`} role="alert">
          {error}
        </span>
      )}
      {asking && (
        <ConfirmSheet
          title="지금 회의를 기록할까요?"
          body="잡힌 회의가 없어도 바로 시작해요. 끝나면 지난 회의 목록에 들어가요."
          okLabel="기록 시작"
          irreversible={false}
          input={{ label: '회의 주제', placeholder: '예: 발표 순서 정하기 (비워 둬도 돼요)' }}
          onClose={({ ok, value }) => {
            setAsking(false)
            if (ok) open(value)
          }}
        />
      )}
    </>
  )
}
