import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Dayjs } from 'dayjs'
import { messageOf } from '../api/client.ts'
import { getRoom } from '../api/rooms.ts'
import { startScheduling } from '../api/scheduling.ts'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import Segmented from '../components/Segmented.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useClock } from '../hooks/useClock.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { formatDuration, toIsoDate } from '../lib/date.ts'
import { PATHS, pathTo } from '../lib/paths.ts'
import type { Room } from '../types/room.ts'
import type { SchedulingInput } from '../types/scheduling.ts'
import form from './Form.module.css'

const MODES = ['대면', '비대면', '상관없음'] as const
const STEP_MIN = 30 // 회의 길이는 30분 단위
const MAX_MIN = 240

// 다음 주 월~금을 기본 기간으로 둔다(회의는 주 1회쯤)
function defaultInput(now: Dayjs): SchedulingInput {
  const monday = now.add(1, 'week').day(1)
  return {
    topic: '중간 점검 전 회의', // 시연에서 바로 시작하도록 채워 둔다
    windowStart: toIsoDate(monday),
    windowEnd: toIsoDate(monday.add(4, 'day')),
    durationMin: 120,
    mode: '상관없음',
  }
}

// 조율 시작(팀장만): 주제·기간·회의 길이·방식을 정하면 에이전트끼리 시간을 맞춘다
export default function SchedulingNewPage() {
  const user = useCurrentUser()
  const room = useApi(() => getRoom(user.roomId), [user.roomId, user.id])

  if (room.status === 'ready' && room.data.canStartScheduling) return <SchedulingForm room={room.data} />
  return (
    <Screen title="회의 잡기" backTo={PATHS.home}>
      {room.status === 'error' && <RetryBox message={room.message} onRetry={room.reload} />}
      {room.status === 'ready' && (
        <section className="sec">
          <h2>회의 잡기는 팀장만 할 수 있어요</h2>
          <p className="meta">팀장이 회의를 잡으면 알림으로 알려 드리고, 조율 과정을 같이 볼 수 있어요.</p>
        </section>
      )}
    </Screen>
  )
}

function SchedulingForm({ room }: { room: Room }) {
  const navigate = useNavigate()
  const now = useClock()
  const [input, setInput] = useState<SchedulingInput>(() => defaultInput(now))
  const [error, setError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const set = <K extends keyof SchedulingInput>(key: K, value: SchedulingInput[K]) =>
    setInput((prev) => ({ ...prev, [key]: value }))

  const problem = !input.topic.trim()
    ? '주제를 써 주세요.'
    : input.windowStart > input.windowEnd
      ? '끝나는 날이 시작하는 날보다 빨라요.'
      : null

  const start = async () => {
    if (problem) return setError(problem)
    setStarting(true)
    try {
      const scheduling = await startScheduling(room.id, { ...input, topic: input.topic.trim() })
      navigate(pathTo.scheduling(scheduling.id), { replace: true }) // 뒤로 가면 홈으로
    } catch (e) {
      setError(messageOf(e))
      setStarting(false)
    }
  }

  const changeLength = (delta: number) =>
    set('durationMin', Math.min(MAX_MIN, Math.max(STEP_MIN, input.durationMin + delta)))

  return (
    <Screen
      title="회의 잡기"
      backTo={PATHS.home}
      dock={
        <div className="btn-row">
          <button type="button" className="btn primary" disabled={starting} onClick={start}>
            조율 시작
          </button>
        </div>
      }
    >
      <section className="sec">
        <label className={form.label}>
          주제
          <input className="field" value={input.topic} maxLength={40} onChange={(e) => set('topic', e.target.value)} />
        </label>
        <span className={form.label}>언제부터 언제 사이에</span>
        <div className={form.range}>
          <input className="field num" type="date" aria-label="시작하는 날" value={input.windowStart} onChange={(e) => set('windowStart', e.target.value)} />
          <span>–</span>
          <input className="field num" type="date" aria-label="끝나는 날" value={input.windowEnd} onChange={(e) => set('windowEnd', e.target.value)} />
        </div>
        <span className={form.label}>회의 길이 (30분 단위)</span>
        <div className={form.stepper}>
          <button type="button" aria-label="30분 줄이기" disabled={input.durationMin <= STEP_MIN} onClick={() => changeLength(-STEP_MIN)}>
            −
          </button>
          <b className="num" aria-live="polite">
            {formatDuration(input.durationMin)}
          </b>
          <button type="button" aria-label="30분 늘리기" disabled={input.durationMin >= MAX_MIN} onClick={() => changeLength(STEP_MIN)}>
            +
          </button>
        </div>
        <span className={form.label}>방식</span>
        <Segmented label="방식" options={MODES} value={input.mode} onChange={(mode) => set('mode', mode)} />
        {error && (
          <p className={form.error} role="alert">
            {error}
          </p>
        )}
      </section>
      <section className="sec">
        <p className="meta">
          팀원 {room.members.length}명의 에이전트가 각자의 시간표와 조건으로 조율해요. 최대 3라운드, 30초쯤 걸려요.
        </p>
      </section>
    </Screen>
  )
}
