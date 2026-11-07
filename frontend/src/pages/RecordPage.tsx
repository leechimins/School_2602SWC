import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { messageOf } from '../api/client.ts'
import { canRecordLive, getMeeting, liveTranscript, writeTranscript } from '../api/records.ts'
import { getRoom } from '../api/rooms.ts'
import Badge from '../components/Badge.tsx'
import Icon from '../components/Icon.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import Waiting from '../components/Waiting.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { useSummarize } from '../hooks/useSummarize.ts'
import { formatDayLabel, formatTimeRange } from '../lib/date.ts'
import { PATHS, pathTo } from '../lib/paths.ts'
import type { Id } from '../types/common.ts'
import type { MeetingDetail } from '../types/meeting.ts'
import type { Member } from '../types/room.ts'
import styles from './RecordPage.module.css'

// 회의 기록: 받아적기가 기본, 직접 쓰기는 그 아래 작게.
// 받아적기 → 정지 → 말한 사람 확인 → 원문 저장 → 정리(AI) → 회의록. 직접 쓰기 → 원문 저장 → 정리 → 회의록.
// 원문을 먼저 저장하고 정리는 따로 부른다: 정리가 실패해도 원문은 남고 "다시 하기"로 같은 원문을 다시 정리한다.

type Step = 'idle' | 'live' | 'voice' | 'paste'
type Heard = { speakerId: Id; text: string }

const LIVE_MS = 3_000 // 받아적는 중 한 줄이 쌓이는 간격(시연용)
const VOICE_NAMES = 'ABCDEFGH'

export default function RecordPage() {
  const { meetingId = '' } = useParams()
  const user = useCurrentUser()
  const res = useApi(() => getMeeting(user.roomId, meetingId), [user.roomId, meetingId])
  const room = useApi(() => getRoom(user.roomId), [user.roomId, user.id])

  return (
    <Screen title="회의 기록" backTo={PATHS.schedule}>
      {res.status === 'error' && <RetryBox message={res.message} onRetry={res.reload} />}
      {res.status === 'ready' && room.status === 'ready' && <Recorder meeting={res.data} members={room.data.members} />}
    </Screen>
  )
}

function Recorder({ meeting: m, members }: { meeting: MeetingDetail; members: Member[] }) {
  const user = useCurrentUser()
  const navigate = useNavigate()
  const [step, setStep] = useState<Step>('idle')
  const [heard, setHeard] = useState<Heard[]>([])
  const [saved, setSaved] = useState(false) // 원문 저장이 끝났는지. 정리가 실패해도 이건 남는다
  const [error, setError] = useState('')
  const summarize = useSummarize(user.roomId, m.id)

  // 원문 저장 → 정리 → 회의록으로. 정리만 실패하면 이 화면에 남아 다시 하기를 보여 준다
  const finish = async (text: string) => {
    if (!saved) {
      try {
        await writeTranscript(user.roomId, m.id, text)
      } catch (e) {
        return setError(messageOf(e)) // 원문 저장부터 실패: 쓴 글은 화면에 그대로 두고 다시 누르게 한다
      }
      setSaved(true)
      setError('')
    }
    if (await summarize.run()) navigate(pathTo.meeting(m.id), { replace: true })
  }

  const head = (
    <section className="sec">
      <p className={styles.topic}>{m.topic}</p>
      <p className="meta num">
        {formatDayLabel(m.startAt)} {formatTimeRange(m.startAt, m.endAt)} · {m.mode} · 참석 {m.attendees.length}명
      </p>
      {error && (
        <p className="meta" role="alert">
          {error}
        </p>
      )}
    </section>
  )

  // 이미 기록한 회의: 다시 받아적지 않고 회의록으로 보낸다
  if (m.transcript.length > 0 && !saved) {
    return (
      <>
        {head}
        <section className="sec">
          <p className="strong">이미 기록한 회의예요</p>
          <Link to={pathTo.meeting(m.id)} className="btn small block">
            회의록 보기
          </Link>
        </section>
      </>
    )
  }

  if (summarize.phase === 'working') {
    return (
      <>
        {head}
        <section className="sec">
          <Waiting what="회의록을 정리하고 할 일을 뽑는 중이에요" detail="원문은 먼저 저장했어요. 지난 할 일 중 끝났다고 한 것도 같이 찾아요." />
        </section>
      </>
    )
  }

  if (summarize.phase === 'failed') {
    return (
      <>
        {head}
        <section className="sec">
          <Badge tone="warn">정리 못 함</Badge>
          <p className="strong">잠시 후 다시 해 주세요.</p>
          <p className="meta">받아적은 원문은 저장했어요. 다시 하면 그 원문으로 정리해요.</p>
          <div className="btn-row">
            <Link to={pathTo.meeting(m.id)} className="btn quiet">
              원문 보기
            </Link>
            <button type="button" className="btn primary" onClick={() => finish('')}>
              다시 하기
            </button>
          </div>
        </section>
      </>
    )
  }

  return (
    <>
      {head}
      {step === 'idle' && !canRecordLive() && (
        <section className="sec">
          <p className="strong">회의 기록</p>
          <p className="meta">회의에서 나온 말을 붙여 넣으면 에이전트가 요약하고 할 일을 뽑아 제안해요.</p>
          <button type="button" className={`btn primary block ${styles.big}`} onClick={() => setStep('paste')}>
            회의록 직접 쓰기
          </button>
        </section>
      )}
      {step === 'idle' && canRecordLive() && (
        <section className="sec">
          <p className="strong">회의 기록</p>
          <p className="meta">할 일 제안은 회의가 끝난 뒤 회의록에서 확정해야 할 일 탭에 들어가요.</p>
          <button type="button" className={`btn primary block ${styles.big}`} onClick={() => setStep('live')}>
            <Icon name="mic" />
            받아적기 시작
          </button>
          <p className={`meta ${styles.center}`}>음성은 저장하지 않고 글자만 남겨요</p>
          <div className={styles.center}>
            <button type="button" className="link" onClick={() => setStep('paste')}>
              직접 쓰기
            </button>
          </div>
        </section>
      )}
      {step === 'live' && (
        <Live
          memberCount={m.attendees.length}
          onStop={(lines) => {
            setHeard(lines)
            setStep(lines.length ? 'voice' : 'idle')
          }}
        />
      )}
      {step === 'voice' && <VoiceCheck heard={heard} members={members} onDone={finish} />}
      {step === 'paste' && <Paste onCancel={() => setStep('idle')} onDone={finish} />}
    </>
  )
}

// 받아적는 중: 빨간 점 + "받아적는 중" + 경과 시간 + 쌓이는 글. 표시가 늘 보여 숨기지 않는다
function Live({ memberCount, onStop }: { memberCount: number; onStop: (lines: Heard[]) => void }) {
  const [seconds, setSeconds] = useState(0)
  const [script] = useState(liveTranscript)
  const lines = script.slice(0, Math.floor((seconds * 1000) / LIVE_MS))
  const voices = [...new Set(script.map((l) => l.speakerId))]
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const id = setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => clearInterval(id)
  }, [])

  // 새 줄이 쌓이면 맨 아래가 보이게
  useEffect(() => {
    box.current?.scrollTo({ top: box.current.scrollHeight })
  }, [lines.length])

  const mm = String(Math.floor(seconds / 60)).padStart(2, '0')
  const ss = String(seconds % 60).padStart(2, '0')
  return (
    <section className="sec">
      <div className="row-between">
        <span className={styles.recDot}>받아적는 중</span>
        <span className="meta">참석 {memberCount}명</span>
      </div>
      <p className={`${styles.clock} num`} aria-label={`${seconds}초 지남`}>
        {mm}:{ss}
      </p>
      <p className="meta">음성은 저장하지 않고 글자만 남겨요.</p>
      <div ref={box} className={styles.live} aria-live="polite">
        {lines.length === 0 ? (
          <p className="meta">말을 시작하면 여기에 글자로 쌓여요</p>
        ) : (
          <ol className={styles.lines}>
            {lines.map((l, i) => (
              <li key={i} className={styles.line}>
                <b>{VOICE_NAMES[voices.indexOf(l.speakerId)]}</b>
                <span>{l.text}</span>
              </li>
            ))}
          </ol>
        )}
      </div>
      <p className="meta">말한 사람은 목소리로 나눠 두고, 끝나면 누군지 한 번만 골라요.</p>
      <button type="button" className="btn primary block" onClick={() => onStop(lines)}>
        정지
      </button>
    </section>
  )
}

// 말한 사람 확인: 목소리마다 누군지 한 번만 고르면 원문 전체에 반영된다
function VoiceCheck({ heard, members, onDone }: { heard: Heard[]; members: Member[]; onDone: (text: string) => void }) {
  const voices = [...new Set(heard.map((l) => l.speakerId))]
  const [who, setWho] = useState<Record<Id, Id>>(() => Object.fromEntries(voices.map((v) => [v, v])))
  const nameOf = (voice: Id) => members.find((x) => x.id === who[voice])?.name ?? ''

  return (
    <section className="sec">
      <h2>말한 사람 확인</h2>
      <p className="meta">목소리 {voices.length}개로 나눴어요. 누군지 한 번만 고르면 회의록 전체에 반영돼요.</p>
      {voices.map((v, i) => (
        <div key={v} className={styles.voice}>
          <div>
            <p className="strong">목소리 {VOICE_NAMES[i]}</p>
            <p className="meta">'{heard.find((l) => l.speakerId === v)?.text}'</p>
          </div>
          <select
            className="field"
            aria-label={`목소리 ${VOICE_NAMES[i]}는 누구`}
            value={who[v]}
            onChange={(e) => setWho({ ...who, [v]: e.target.value })}
          >
            {members.map((x) => (
              <option key={x.id} value={x.id}>
                {x.name}
              </option>
            ))}
          </select>
        </div>
      ))}
      <button
        type="button"
        className="btn primary block"
        onClick={() => onDone(heard.map((l) => `${nameOf(l.speakerId)}: ${l.text}`).join('\n'))}
      >
        맞아요, 정리하기
      </button>
    </section>
  )
}

// 직접 쓰기: 받아적기가 안 될 때(마이크 없음, 조용히 해야 할 때)의 보조 길. AI 없이도 원문은 저장된다
function Paste({ onCancel, onDone }: { onCancel: () => void; onDone: (text: string) => void }) {
  const [text, setText] = useState('')
  return (
    <section className="sec">
      <h2>회의록 직접 쓰기</h2>
      <p className="meta">메모나 다른 곳에 적은 회의록을 붙여 넣으세요. 한 줄에 한 말, "이름: 말"로 쓰면 말한 사람이 남아요.</p>
      <textarea
        className={`field ${styles.paste}`}
        aria-label="회의록"
        value={text}
        placeholder={'민지: 발표 구성안은 제가 금요일까지 만들게요\n현우: 시연은 제가 맡을게요'}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="btn-row">
        <button type="button" className="btn quiet" onClick={onCancel}>
          취소
        </button>
        <button type="button" className="btn primary" disabled={!text.trim()} onClick={() => onDone(text)}>
          정리하기
        </button>
      </div>
    </section>
  )
}
