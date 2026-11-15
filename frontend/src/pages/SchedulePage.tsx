import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { messageOf } from '../api/client.ts'
import { createMeeting, getMeeting } from '../api/records.ts'
import { getRoom } from '../api/rooms.ts'
import { getSchedule } from '../api/scheduling.ts'
import AiMark from '../components/AiMark.tsx'
import Badge from '../components/Badge.tsx'
import ConfirmSheet from '../components/ConfirmSheet.tsx'
import DateBlock from '../components/DateBlock.tsx'
import EmptyState from '../components/EmptyState.tsx'
import Icon from '../components/Icon.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useClock } from '../hooks/useClock.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import {
  formatDuration,
  formatRange,
  formatTimeRange,
  isSameDay,
  minutesBetween,
} from '../lib/date.ts'
import { answerLine, isAdhoc } from '../lib/meeting.ts'
import { pathTo } from '../lib/paths.ts'
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
        <ScheduleBody
          schedule={res.data}
          canStartScheduling={room.status === 'ready' && room.data.canStartScheduling}
          total={room.status === 'ready' ? room.data.joinedCount : null}
        />
      )}
    </Screen>
  )
}

type BodyProps = { schedule: Schedule; canStartScheduling: boolean; total: number | null }

function ScheduleBody({ schedule, canStartScheduling, total }: BodyProps) {
  const now = useClock()
  const { coordinating, upcoming, past } = schedule
  // 오늘 잡힌 확정 회의가 있으면 "지금 회의 받아적기"가 그 회의에 붙는다
  const today = upcoming.find((m) => m.status === 'confirmed' && isSameDay(m.startAt, now))
  // 오늘 회의를 이미 기록했으면 "기록 시작" 대신 "회의록 보기". 일정 목록에는 기록 여부가 없어 그 회의만 따로 본다
  const user = useCurrentUser()
  const todayDetail = useApi(
    () => (today ? getMeeting(user.roomId, today.id) : Promise.resolve(null)),
    [user.roomId, user.id, today?.id],
  )
  const recorded = todayDetail.status === 'ready' && !!todayDetail.data && todayDetail.data.transcript.length > 0
  // 지난 회의도 기록했는지는 회의마다 따로 본다. 시간만 지나고 기록 안 한 회의는 "기록하기"로 보낸다
  const pastIds = past.map((m) => m.id)
  const pastDetails = useApi(
    () => Promise.all(pastIds.map((id) => getMeeting(user.roomId, id))),
    [user.roomId, user.id, pastIds.join()],
  )
  const recordedPast = (id: string) =>
    pastDetails.status === 'ready' ? pastDetails.data.some((d) => d.id === id && d.transcript.length > 0) : null

  return (
    <>
      <RecordNow todayMeeting={recorded ? null : (today ?? null)} />

      {coordinating.length > 0 && (
        <>
          <div className="sec-h">
            <h2>조율 중인 회의</h2>
          </div>
          <section className="sec">
            {coordinating.map((c) => (
              <Link key={c.id} to={pathTo.scheduling(c.id)} className={styles.row}>
                <DateBlock muted />
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
      </div>
      <section className="sec">
        {upcoming.length === 0 ? (
          <EmptyState
            title="잡힌 회의가 없어요"
            description={canStartScheduling ? '새 회의는 홈에서 잡아요.' : '팀장이 회의를 잡으면 알려 드려요.'}
          />
        ) : (
          upcoming.map((m) => (
            <UpcomingRow key={m.id} meeting={m} isToday={m.id === today?.id} recorded={recorded} total={total} />
          ))
        )}
      </section>

      <div className="sec-h">
        <h2>지난 회의</h2>
        <span className="meta num">{past.length}개</span>
      </div>
      <section className="sec">
        {past.length === 0 ? (
          // 다음 행동(지금 회의 기록하기)은 화면 맨 위 카드에 있어 버튼을 또 두지 않는다
          <EmptyState
            title="아직 지난 회의가 없어요"
            description="회의를 기록하면 요약과 할 일 제안이 여기에 쌓여요."
          />
        ) : (
          past.map((m) => <PastRow key={m.id} meeting={m} recorded={recordedPast(m.id)} />)
        )}
      </section>
    </>
  )
}

// 지난 회의 한 줄: 기록했으면 회의록으로, 시간만 지나고 기록 안 했으면 기록 화면으로. 확인 전(null)에는 버튼을 비운다
function PastRow({ meeting: m, recorded }: { meeting: MeetingBrief; recorded: boolean | null }) {
  return (
    <Link to={recorded === false ? pathTo.record(m.id) : pathTo.meeting(m.id)} className={styles.row}>
      <DateBlock at={m.startAt} muted />
      <span className={styles.body}>
        <span className="strong">{m.topic}</span>
        <span className="meta num">
          {formatDuration(minutesBetween(m.startAt, m.endAt))} · {m.mode}
        </span>
        {m.suggestionCount > 0 && (
          <span className={styles.mark}>
            <AiMark label={`제안 ${m.suggestionCount}개`} />
          </span>
        )}
      </span>
      {/* 줄 전체가 링크라 버튼은 모양만 낸다(링크 안에 링크를 넣지 않음) */}
      {recorded !== null && <span className="btn small">{recorded ? '회의록 보기' : '기록하기'}</span>}
    </Link>
  )
}

type RowProps = { meeting: MeetingBrief; isToday: boolean; recorded: boolean; total: number | null }

// 잡힌 회의 한 줄: 누르면 조율 결과로. 바로 기록한 회의는 조율 결과가 없어 기록 화면으로(기록 시작과 같은 곳).
// 오늘 회의면 오른쪽에 기록 시작(기록했으면 회의록 보기)
function UpcomingRow({ meeting: m, isToday, recorded, total }: RowProps) {
  const confirmed = m.status === 'confirmed'
  const line = answerLine(m, total)
  return (
    <div className={styles.row}>
      <Link to={isAdhoc(m) ? pathTo.record(m.id) : pathTo.proposal(m.id)} className={styles.main}>
        <DateBlock at={m.startAt} />
        <span className={styles.body}>
          <span className="strong">{m.topic}</span>
          <span className="meta num">
            {formatTimeRange(m.startAt, m.endAt)} · {m.mode} · {formatDuration(minutesBetween(m.startAt, m.endAt))}
          </span>
          <span className="meta">{line}</span>
        </span>
      </Link>
      {isToday && recorded ? (
        <Link to={pathTo.meeting(m.id)} className="btn small">
          회의록 보기
        </Link>
      ) : isToday ? (
        <Link to={pathTo.record(m.id)} className="btn small primary">
          기록 시작
        </Link>
      ) : (
        <Badge tone={confirmed ? 'ok' : 'warn'}>{confirmed ? '확정' : '확정 대기'}</Badge>
      )}
    </div>
  )
}

// 지금 회의 기록하기: 오늘 잡힌 회의가 있으면 거기에 붙고, 없으면 주제 한 줄(필수)만 받고 바로 연다
function RecordNow({ todayMeeting }: { todayMeeting: MeetingBrief | null }) {
  const user = useCurrentUser()
  const navigate = useNavigate()
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState('')

  const open = async (topic: string) => {
    try {
      const id = await createMeeting(user.roomId, { meetingId: null, topic, mode: '대면' })
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
          <b>지금 회의 기록하기</b>
          <span>
            {todayMeeting
              ? `오늘 ${formatTimeRange(todayMeeting.startAt, todayMeeting.endAt)} ‘${todayMeeting.topic}’`
              : '주제만 정하고 바로 시작'}
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
          okLabel="기록 시작"
          irreversible={false}
          input={{ label: '회의 주제', placeholder: '예: 발표 순서 정하기', required: '회의 주제를 적어 주세요.' }}
          onClose={({ ok, value }) => {
            setAsking(false)
            if (ok) open(value)
          }}
        />
      )}
    </>
  )
}
