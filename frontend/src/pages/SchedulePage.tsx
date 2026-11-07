import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { messageOf } from '../api/client.ts'
import { canRecordLive, createMeeting } from '../api/records.ts'
import { getRoom } from '../api/rooms.ts'
import { getSchedule } from '../api/scheduling.ts'
import AiMark from '../components/AiMark.tsx'
import Badge from '../components/Badge.tsx'
import ConfirmSheet from '../components/ConfirmSheet.tsx'
import Icon from '../components/Icon.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useClock } from '../hooks/useClock.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import {
  dateParts,
  formatDuration,
  formatRange,
  formatTimeRange,
  isSameDay,
  minutesBetween,
} from '../lib/date.ts'
import { PATHS, pathTo } from '../lib/paths.ts'
import type { IsoDateTime } from '../types/common.ts'
import type { MeetingBrief, Schedule } from '../types/meeting.ts'
import styles from './SchedulePage.module.css'

// 일정 탭: 정해진 회의를 관리하는 화면. 지금 회의 받아적기 → 조율 중 → 잡힌 회의 → 지난 회의(회의록).
// 홈은 기간과 다음 회의 하나만, 여기서는 지난 것까지 전부를 시간 순으로 본다.
export default function SchedulePage() {
  const user = useCurrentUser()
  const res = useApi(() => getSchedule(user.roomId), [user.roomId, user.id])
  const room = useApi(() => getRoom(user.roomId), [user.roomId, user.id])

  return (
    <Screen title="일정">
      {res.status === 'error' && <RetryBox message={res.message} onRetry={res.reload} />}
      {res.status === 'ready' && (
        <ScheduleBody schedule={res.data} canStartScheduling={room.status === 'ready' && room.data.canStartScheduling} />
      )}
    </Screen>
  )
}

function ScheduleBody({ schedule, canStartScheduling }: { schedule: Schedule; canStartScheduling: boolean }) {
  const now = useClock()
  const { coordinating, upcoming, past } = schedule
  // 오늘 잡힌 확정 회의가 있으면 "지금 회의 받아적기"가 그 회의에 붙는다
  const today = upcoming.find((m) => m.status === 'confirmed' && isSameDay(m.startAt, now))

  return (
    <>
      <RecordNow todayMeeting={today ?? null} />

      {coordinating.length > 0 && (
        <>
          <div className="sec-h">
            <h2>조율 중인 회의</h2>
          </div>
          <section className="sec">
            {coordinating.map((c) => (
              <Link key={c.id} to={pathTo.scheduling(c.id)} className={styles.row}>
                <span className={`${styles.date} ${styles.muted}`}>
                  <b>–</b>
                </span>
                <span className={styles.body}>
                  <span className="strong">{c.topic}</span>
                  <span className="meta num">조율 중 · {formatRange(c.windowStart, c.windowEnd)} 사이</span>
                </span>
                <Badge>조율 중</Badge>
              </Link>
            ))}
          </section>
        </>
      )}

      <div className="sec-h">
        <h2>잡힌 회의</h2>
        {canStartScheduling && (
          <Link to={PATHS.schedulingNew} className={`link ${styles.secLink}`}>
            + 새 회의 잡기
          </Link>
        )}
      </div>
      <section className="sec">
        {upcoming.length === 0 ? (
          <p className="meta">
            잡힌 회의가 없어요.{' '}
            {canStartScheduling ? '새 회의를 잡으면 에이전트끼리 시간을 조율해요.' : '팀장이 회의를 잡으면 알려 드려요.'}
          </p>
        ) : (
          upcoming.map((m) => <UpcomingRow key={m.id} meeting={m} isToday={m.id === today?.id} />)
        )}
      </section>

      <div className="sec-h">
        <h2>지난 회의</h2>
        <span className="meta num">{past.length}개</span>
      </div>
      <section className="sec">
        {past.length === 0 ? (
          <p className="meta">아직 지난 회의가 없어요. 회의를 기록하면 요약과 할 일 제안이 여기에 쌓여요.</p>
        ) : (
          past.map((m) => (
            <Link key={m.id} to={pathTo.meeting(m.id)} className={styles.row}>
              <DateBlock at={m.startAt} muted />
              <span className={styles.body}>
                <span className="strong">{m.topic}</span>
                <span className="meta num">
                  {formatDuration(minutesBetween(m.startAt, m.endAt))} · {m.mode} · 회의록 열기
                </span>
              </span>
              {m.suggestionCount > 0 && <AiMark label={`제안 ${m.suggestionCount}개`} />}
            </Link>
          ))
        )}
      </section>
    </>
  )
}

// 날짜 칸: 잡힌 회의는 포인트색, 지난 회의는 회색
function DateBlock({ at, muted = false }: { at: IsoDateTime; muted?: boolean }) {
  const { month, day, weekday } = dateParts(at)
  return (
    <span className={`${styles.date} ${muted ? styles.muted : ''} num`}>
      <small>{month}</small>
      <b>{day}</b>
      <small>{weekday}</small>
    </span>
  )
}

// 잡힌 회의 한 줄: 누르면 조율 결과로. 오늘 회의면 오른쪽에 기록 시작
function UpcomingRow({ meeting: m, isToday }: { meeting: MeetingBrief; isToday: boolean }) {
  const confirmed = m.status === 'confirmed'
  const line = confirmed
    ? '모두 수락했어요'
    : `아직 응답 ${m.pendingCount}명${m.myState ? ` · 내 응답 ${m.myState}` : ''}`
  return (
    <div className={styles.row}>
      <Link to={pathTo.proposal(m.id)} className={styles.main}>
        <DateBlock at={m.startAt} />
        <span className={styles.body}>
          <span className="strong">{m.topic}</span>
          <span className="meta num">
            {formatTimeRange(m.startAt, m.endAt)} · {m.mode} · {formatDuration(minutesBetween(m.startAt, m.endAt))}
          </span>
          <span className="meta">{line}</span>
        </span>
      </Link>
      {isToday ? (
        <Link to={pathTo.record(m.id)} className="btn small primary">
          기록 시작
        </Link>
      ) : (
        <Badge tone={confirmed ? 'ok' : 'warn'}>{confirmed ? '확정' : '확정 대기'}</Badge>
      )}
    </div>
  )
}

// 지금 회의 받아적기(실서버는 기록하기): 오늘 잡힌 회의가 있으면 거기에 붙고, 없으면 주제 한 줄(비워도 됨)만 받고 바로 연다
function RecordNow({ todayMeeting }: { todayMeeting: MeetingBrief | null }) {
  const user = useCurrentUser()
  const navigate = useNavigate()
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState('')
  // 실서버는 받아적기가 없어 직접 쓰기만 연다(api/records.ts canRecordLive). 문구도 그에 맞춘다
  const live = canRecordLive()
  const label = live ? '지금 회의 받아적기' : '지금 회의 기록하기'
  const verb = live ? '받아적어요' : '기록해요'

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
        className={styles.recNow}
        onClick={() => (todayMeeting ? navigate(pathTo.record(todayMeeting.id)) : setAsking(true))}
      >
        <span className={styles.recIcon}>
          <Icon name="mic" />
        </span>
        <span>
          <b>{label}</b>
          <span>
            {todayMeeting
              ? `오늘 ${formatTimeRange(todayMeeting.startAt, todayMeeting.endAt)} '${todayMeeting.topic}' 회의를 ${verb}`
              : `잡힌 회의가 없어도 주제 한 줄만 쓰고 바로 ${verb}`}
          </span>
        </span>
      </button>
      {error && (
        <p className={`meta ${styles.error}`} role="alert">
          {error}
        </p>
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
