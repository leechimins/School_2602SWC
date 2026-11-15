import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { messageOf } from '../api/client.ts'
import { getMeeting, writeTranscript } from '../api/records.ts'
import { getRoom } from '../api/rooms.ts'
import Badge from '../components/Badge.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import Waiting from '../components/Waiting.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { useSummarize } from '../hooks/useSummarize.ts'
import { formatDayLabel, formatTimeRange } from '../lib/date.ts'
import { PATHS, pathTo } from '../lib/paths.ts'
import type { MeetingDetail } from '../types/meeting.ts'
import type { Member } from '../types/room.ts'
import styles from './RecordPage.module.css'

// 회의 기록: 직접 쓰기(붙여 넣기) → 원문 저장 → 정리(AI) → 회의록.
// 원문을 먼저 저장하고 정리는 따로 부른다: 정리가 실패해도 원문은 남고 "다시 하기"로 같은 원문을 다시 정리한다.

type Step = 'idle' | 'paste'

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
  const [saved, setSaved] = useState(false) // 원문 저장이 끝났는지. 정리가 실패해도 이건 남는다
  const [error, setError] = useState('')
  const summarize = useSummarize(user.roomId, m.id)

  // 조율로 잡힌 회의는 수락한 사람 수, 바로 기록하는 회의는 수락한 사람이 없어 팀원 수를 보인다
  const people = m.attendees.length > 0 ? `참석 ${m.attendees.length}명` : `팀원 ${members.length}명`

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
        {formatDayLabel(m.startAt)} {formatTimeRange(m.startAt, m.endAt)} · {m.mode} · {people}
      </p>
      {error && (
        <p className="meta" role="alert">
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
          <p className="meta">쓴 원문은 저장했어요. 다시 하면 그 원문으로 정리해요.</p>
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
      {step === 'idle' && (
        <section className="sec">
          <p className="strong">회의 기록</p>
          <p className="meta">회의에서 나온 말을 붙여 넣으면 에이전트가 요약하고 할 일을 뽑아 제안해요.</p>
          <button type="button" className={`btn primary block ${styles.big}`} onClick={() => setStep('paste')}>
            회의록 직접 쓰기
          </button>
        </section>
      )}
      {step === 'paste' && <Paste onCancel={() => setStep('idle')} onDone={finish} />}
    </>
  )
}

// 직접 쓰기: AI 없이도 원문은 저장된다
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
