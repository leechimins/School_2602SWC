import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { Dayjs } from 'dayjs'
import { messageOf } from '../api/client.ts'
import { getRoom } from '../api/rooms.ts'
import { startScheduling } from '../api/scheduling.ts'
import FieldError, { type FormProblem } from '../components/FieldError.tsx'
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
    topic: '',
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
  const [params] = useSearchParams()
  // 홈의 에이전트 제안에서 오면 주제·기간이 채워져 온다. 날짜 모양이 아니면 기본값
  const [input, setInput] = useState<SchedulingInput>(() => {
    const base = defaultInput(now)
    const day = (v: string | null) => (v && /^\d{4}-\d{2}-\d{2}$/.test(v) ? v : null)
    return {
      ...base,
      topic: (params.get('topic') ?? '').slice(0, 100),
      windowStart: day(params.get('from')) ?? base.windowStart,
      windowEnd: day(params.get('to')) ?? base.windowEnd,
    }
  })
  const [problem, setProblem] = useState<FormProblem>(null)
  const [starting, setStarting] = useState(false)
  const set = <K extends keyof SchedulingInput>(key: K, value: SchedulingInput[K]) =>
    setInput((prev) => ({ ...prev, [key]: value }))

  const invalid: FormProblem = !input.topic.trim()
    ? { at: 'topic', message: '주제를 써 주세요.' }
    : input.windowStart > input.windowEnd
      ? { at: 'window', message: '끝나는 날이 시작하는 날보다 빨라요.' }
      : null

  const start = async () => {
    if (invalid) return setProblem(invalid)
    setStarting(true)
    try {
      const scheduling = await startScheduling(room.id, { ...input, topic: input.topic.trim() })
      navigate(pathTo.scheduling(scheduling.id), { replace: true }) // 뒤로 가면 홈으로
    } catch (e) {
      setProblem({ at: 'end', message: messageOf(e) })
      setStarting(false)
    }
  }

  const changeLength = (delta: number) =>
    set('durationMin', Math.min(MAX_MIN, Math.max(STEP_MIN, input.durationMin + delta)))

  return (
    <Screen
      title="회의 잡기"
      backTo={PATHS.home}
      bareDock
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
          <input className="field" value={input.topic} maxLength={40} placeholder="예: 중간 점검 전 회의" onChange={(e) => set('topic', e.target.value)} />
        </label>
        <FieldError problem={problem} at="topic" />
        <span className={form.label}>기간</span>
        <div className={form.range}>
          <input className="field num" type="date" aria-label="시작하는 날" value={input.windowStart} onChange={(e) => set('windowStart', e.target.value)} />
          <span>–</span>
          <input className="field num" type="date" aria-label="끝나는 날" value={input.windowEnd} onChange={(e) => set('windowEnd', e.target.value)} />
        </div>
        <FieldError problem={problem} at="window" />
        <span className={form.label}>소요 시간</span>
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
        <FieldError problem={problem} at="end" />
      </section>
    </Screen>
  )
}
