import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { messageOf } from '../api/client.ts'
import { getMeeting, mapSpeakers, startRecording, uploadRecording, writeTranscript } from '../api/records.ts'
import { getRoom } from '../api/rooms.ts'
import Badge from '../components/Badge.tsx'
import Icon from '../components/Icon.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import Waiting from '../components/Waiting.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { useRecorder } from '../hooks/useRecorder.ts'
import { useSummarize } from '../hooks/useSummarize.ts'
import { formatDayLabel, formatTimeRange } from '../lib/date.ts'
import { PATHS, pathTo } from '../lib/paths.ts'
import type { Id } from '../types/common.ts'
import type { MeetingDetail, TranscriptLine } from '../types/meeting.ts'
import type { Member } from '../types/room.ts'
import form from './Form.module.css'
import styles from './RecordPage.module.css'

// 회의 기록: 녹음이 기본, 직접 쓰기는 그 아래 작게.
//   녹음 → 끝내기 → 서버가 받아적음(목소리 A·B…) → 말한 사람 확인 → 정리(AI) → 회의록
//   직접 쓰기("이름: 말" 줄) → 원문 저장 → 정리(AI) → 회의록
// 원문을 먼저 저장하고 정리는 따로 부른다: 정리가 실패해도 원문은 남고 "다시 하기"로 같은 원문을 다시 정리한다.

type Step = 'idle' | 'recording' | 'uploading' | 'upload-failed' | 'voice' | 'paste'

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
  const recorder = useRecorder()
  const [step, setStep] = useState<Step>('idle')
  const [audio, setAudio] = useState<Blob | null>(null) // 올리다 실패하면 같은 녹음으로 다시 올린다
  const [heard, setHeard] = useState<TranscriptLine[]>([])
  const [saved, setSaved] = useState(false) // 원문 저장이 끝났는지. 정리가 실패해도 이건 남는다
  const [error, setError] = useState('')
  const summarize = useSummarize(user.roomId, m.id)

  // 조율로 잡힌 회의는 수락한 사람 수, 바로 기록하는 회의는 수락한 사람이 없어 팀원 수를 보인다
  const people = m.attendees.length > 0 ? `참석 ${m.attendees.length}명` : `팀원 ${members.length}명`

  const summarizeAndOpen = async () => {
    if (await summarize.run()) navigate(pathTo.meeting(m.id), { replace: true })
  }

  // 직접 쓰기: 원문 저장 → 정리 → 회의록으로. 정리만 실패하면 이 화면에 남아 다시 하기를 보여 준다
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
    await summarizeAndOpen()
  }

  const record = async () => {
    setError('')
    try {
      await startRecording(user.roomId, m.id)
      await recorder.start()
      setStep('recording')
    } catch (e) {
      setError(messageOf(e))
    }
  }

  const upload = async (blob: Blob) => {
    setAudio(blob)
    setStep('uploading')
    setError('')
    try {
      const detail = await uploadRecording(user.roomId, m.id, blob)
      setSaved(true)
      setHeard(detail.transcript)
      // 목소리를 못 나눴으면 고를 것이 없어 바로 정리한다
      if (detail.transcript.some((l) => l.speakerLabel)) setStep('voice')
      else await summarizeAndOpen()
    } catch (e) {
      setError(messageOf(e))
      setStep('upload-failed')
    }
  }

  const confirmVoices = async (labels: Record<string, Id | null>) => {
    try {
      await mapSpeakers(user.roomId, m.id, labels)
    } catch (e) {
      return setError(messageOf(e))
    }
    setError('')
    await summarizeAndOpen()
  }

  const head = (
    <section className="sec">
      <p className={styles.topic}>{m.topic}</p>
      <p className="meta num">
        {formatDayLabel(m.startAt)} {formatTimeRange(m.startAt, m.endAt)} · {m.mode} · {people}
      </p>
      {error && (
        <p className={form.error} role="alert">
          {error}
        </p>
      )}
    </section>
  )

  // 이미 기록한 회의: 다시 쓰지 않고 회의록으로 보낸다
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

  if (summarize.phase === 'working' || step === 'uploading') {
    return (
      <>
        {head}
        <section className="sec">
          <Waiting what={step === 'uploading' ? '녹음을 글로 받아적는 중이에요' : '회의록을 정리하고 할 일을 뽑는 중이에요'} />
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
          <p className="meta">원문은 저장했어요.</p>
          <div className="btn-row">
            <Link to={pathTo.meeting(m.id)} className="btn quiet">
              원문 보기
            </Link>
            <button type="button" className="btn primary" onClick={summarizeAndOpen}>
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
      {step === 'idle' && (
        <section className="sec">
          <button type="button" className={`btn primary block ${styles.big}`} onClick={record}>
            <Icon name="mic" />
            회의 녹음하기
          </button>
          <div className={styles.center}>
            <button type="button" className="link" onClick={() => setStep('paste')}>
              직접 쓰기
            </button>
          </div>
        </section>
      )}
      {step === 'recording' && recorder.startedAt !== null && (
        <Live startedAt={recorder.startedAt} people={people} onStop={() => recorder.stop().then(upload)} />
      )}
      {step === 'upload-failed' && audio && (
        <section className="sec">
          <div className="btn-row">
            <button type="button" className="btn quiet" onClick={() => setStep('paste')}>
              직접 쓰기
            </button>
            <button type="button" className="btn primary" onClick={() => upload(audio)}>
              다시 올리기
            </button>
          </div>
        </section>
      )}
      {step === 'voice' && <VoiceCheck heard={heard} members={members} onDone={confirmVoices} />}
      {step === 'paste' && <Paste members={members} onCancel={() => setStep('idle')} onDone={finish} />}
    </>
  )
}

// 녹음 중: 빨간 점 + "녹음 중" + 지난 시간. 표시가 늘 보여 숨기지 않는다
function Live({ startedAt, people, onStop }: { startedAt: number; people: string; onStop: () => void }) {
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  const seconds = Math.max(0, Math.floor((now - startedAt) / 1000))
  const mm = String(Math.floor(seconds / 60)).padStart(2, '0')
  const ss = String(seconds % 60).padStart(2, '0')

  return (
    <section className="sec">
      <div className="row-between">
        <span className={styles.recDot}>녹음 중</span>
        <span className="meta num">{people}</span>
      </div>
      <p className={`${styles.clock} num`} aria-label={`${seconds}초 지남`}>
        {mm}:{ss}
      </p>
      <button type="button" className="btn primary block" onClick={onStop}>
        녹음 끝내기
      </button>
    </section>
  )
}

type VoiceCheckProps = { heard: TranscriptLine[]; members: Member[]; onDone: (labels: Record<string, Id | null>) => void }

// 말한 사람 확인: 목소리마다 누군지 한 번만 고르면 원문 전체에 반영된다
function VoiceCheck({ heard, members, onDone }: VoiceCheckProps) {
  const voices = [...new Set(heard.flatMap((l) => (l.speakerLabel ? [l.speakerLabel] : [])))].sort()
  const [who, setWho] = useState<Record<string, Id | null>>(() =>
    Object.fromEntries(voices.map((v, i) => [v, members[i]?.id ?? null])),
  )

  return (
    <section className="sec">
      <h2>말한 사람 확인</h2>
      {voices.map((v) => (
        <div key={v} className={styles.voice}>
          <div>
            <p className="strong">목소리 {v}</p>
            <p className="meta">‘{heard.find((l) => l.speakerLabel === v)?.text}’</p>
          </div>
          <select
            className="field"
            aria-label={`목소리 ${v}는 누구`}
            value={who[v] ?? ''}
            onChange={(e) => setWho({ ...who, [v]: e.target.value || null })}
          >
            {members.map((x) => (
              <option key={x.id} value={x.id}>
                {x.name}
              </option>
            ))}
            <option value="">모름</option>
          </select>
        </div>
      ))}
      <button type="button" className={`btn primary block ${styles.voiceDone}`} onClick={() => onDone(who)}>
        정리하기
      </button>
    </section>
  )
}

// 서버(transcript.parse)와 같은 꼴: "이름: 말". 콜론은 반각·전각 둘 다
const SPEAKER_LINE = /^([^:：]{1,20}?)\s*[:：]\s*(\S.*)$/

/** 형식에 안 맞는 첫 줄을 한 줄 안내로. 다 맞으면 null */
function formatProblem(text: string, names: string[]): string | null {
  for (const [i, raw] of text.split('\n').entries()) {
    const line = raw.trim()
    if (!line) continue
    const match = SPEAKER_LINE.exec(line)
    if (!match) return `${i + 1}번째 줄을 "이름: 한 말"로 써 주세요.`
    const name = match[1].trim()
    if (!names.includes(name)) return `${i + 1}번째 줄의 "${name}"은 팀원 이름이 아니에요.`
  }
  return null
}

type PasteProps = { members: Member[]; onCancel: () => void; onDone: (text: string) => void }

// 직접 쓰기: 한 줄에 "팀원 이름: 한 말". 쓰는 동안은 조용하고, 정리하기를 누를 때 틀린 줄을 알려 주고 멈춘다
function Paste({ members, onCancel, onDone }: PasteProps) {
  const [text, setText] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const submit = () => {
    const found = formatProblem(text, members.map((x) => x.name))
    if (found) return setProblem(found)
    onDone(text)
  }
  return (
    <section className="sec">
      <h2>회의록 직접 쓰기</h2>
      <textarea
        className={`field ${styles.paste}`}
        aria-label="회의록"
        aria-invalid={problem !== null}
        value={text}
        placeholder={'이름: 한 말\n이름: 한 말'}
        onChange={(e) => {
          setText(e.target.value)
          setProblem(null)
        }}
      />
      {problem && (
        <p className={form.error} role="alert">
          {problem}
        </p>
      )}
      <div className="btn-row">
        <button type="button" className="btn quiet" onClick={onCancel}>
          취소
        </button>
        <button type="button" className="btn primary" disabled={!text.trim()} onClick={submit}>
          정리하기
        </button>
      </div>
    </section>
  )
}
