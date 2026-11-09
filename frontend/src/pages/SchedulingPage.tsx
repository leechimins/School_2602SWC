import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { isRealServer } from '../api/client.ts'
import { getScheduling } from '../api/scheduling.ts'
import AgentBubble from '../components/AgentBubble.tsx'
import Badge from '../components/Badge.tsx'
import Icon from '../components/Icon.tsx'
import JudgeBubble from '../components/JudgeBubble.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import Waiting from '../components/Waiting.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { formatDuration, formatMonthDay, formatRange, formatSlot, formatTimeRange, weekday } from '../lib/date.ts'
import { PATHS, pathTo } from '../lib/paths.ts'
import { UTTERANCE_MS, later } from '../lib/timers.ts'
import type { Tone } from '../lib/tones.ts'
import type { Id } from '../types/common.ts'
import type { Scheduling, SchedulingStatus, Slot, Utterance } from '../types/scheduling.ts'
import styles from './SchedulingPage.module.css'

const MAX_ROUNDS = 3

const STATUS: Record<SchedulingStatus, { label: string; tone: Tone; title: string }> = {
  running: { label: '진행 중', tone: 'here', title: '자동 조율 진행 중' },
  agreed: { label: '합의', tone: 'ok', title: '시간을 정했어요' },
  settled: { label: '조정', tone: 'warn', title: '판단 에이전트가 정했어요' },
  failed: { label: '못 잡음', tone: 'danger', title: '시간을 못 잡았어요' },
}

const STAGES = ['일정 수집', '시간 조율 중', '최종 확정'] as const

const HERO = {
  sub: '팀원의 일정과 선호를 보고 가장 딱 맞는 회의 시간을 찾고 있어요!',
  icon: <Icon name="calendar" />,
}

const slotText = (slot: Slot) => `${formatSlot(slot.startAt, slot.endAt)} · ${slot.mode}`

// 시간 정하는 과정(11/9 TTAK 시안): 왜 이 시간이 나왔는지 보여 준다. 앱에서 가장 중요한 화면이다.
// 상태 카드(단계 바·라운드) → 라운드 타임라인 → 에이전트 대화 → (진행 중이면) 캐릭터 안내 → 하단 확정 카드.
// 라운드마다 개인 에이전트 어필 → 판단 에이전트가 하나를 고름 → 개인 에이전트 수락·거절. 에이전트가 모두 수락하면 사람이 수락·거절한다
// 발언 목록을 한 번에 받아 1.6초마다 하나씩 쌓는다. 스피너로 덮지 않고, 단계 바·라운드가 같이 오른다.
export default function SchedulingPage() {
  const { schedulingId } = useParams()
  const user = useCurrentUser()
  const res = useApi(() => getScheduling(user.roomId, schedulingId ?? ''), [user.roomId, user.id, schedulingId])

  // 실서버에서는 조율이 뒷단에서 돈다. 도는 동안 발언 간격마다 다시 불러, 새로 쌓인 발언을 Talk가 이어서 재생한다.
  // 목은 가짜 서버가 끝날 때 저장소가 바뀌어 useApi가 알아서 다시 부르므로 필요 없다.
  const running = res.status === 'ready' && res.data.status === 'running'
  const { reload } = res
  useEffect(() => {
    if (!running || !isRealServer()) return
    return later(reload, UTTERANCE_MS)
  }, [running, reload, res])

  if (!schedulingId) return <Navigate to={PATHS.home} replace />
  if (res.status === 'ready') {
    return <Talk key={res.data.id} scheduling={res.data} viewerId={user.id} isLeader={user.isLeader} />
  }
  return (
    <Screen title="회의 조율" hero={HERO} backTo={PATHS.home}>
      {res.status === 'loading' && <Waiting what="에이전트들이 모이고 있어요" />}
      {res.status === 'error' && <RetryBox message={res.message} onRetry={res.reload} />}
    </Screen>
  )
}

type TalkProps = {
  scheduling: Scheduling
  viewerId: Id
  isLeader: boolean
}

function Talk({ scheduling: s, viewerId, isLeader }: TalkProps) {
  const total = s.utterances.length
  // 진행 중인 조율은 처음부터 하나씩, 끝난 조율을 다시 열면 전부 보여 준다
  const [shown, setShown] = useState(() => (s.status === 'running' ? 0 : total))
  const playing = shown < total
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (shown >= total) return
    return later(() => setShown((n) => n + 1), shown === 0 ? UTTERANCE_MS / 4 : UTTERANCE_MS)
  }, [shown, total])

  // 새 발언이 나올 때마다 맨 아래로 따라간다
  useEffect(() => {
    if (shown > 0 && playing) endRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
  }, [shown, playing])

  const visible = s.utterances.slice(0, shown)
  const round = visible.at(-1)?.round ?? 1
  // 말이 다 나왔어도 서버가 아직 정리 중이면 진행 중으로 둔다
  const status: SchedulingStatus = playing ? 'running' : s.status
  const lastSlot = s.utterances.findLast((u) => u.slot)?.slot ?? null

  return (
    <Screen
      title="회의 조율"
      hero={HERO}
      backTo={PATHS.home}
      dock={<Dock scheduling={s} status={status} round={round} slot={lastSlot} isLeader={isLeader} />}
    >
      <StatusCard scheduling={s} status={status} round={round} />
      <RoundTimeline utterances={visible} status={status} round={round} roundsUsed={s.roundsUsed} />

      <section className={`sec ${styles.talkCard}`}>
        <h2 className={styles.cardTitle}>
          <span className={styles.titleIcon} aria-hidden="true">
            💬
          </span>
          에이전트 대화
        </h2>
        <div className={styles.talk} aria-live="polite">
          {visible.length === 0 && <p className="meta">에이전트들이 자리에 앉고 있어요…</p>}
          {visible.map((u, i) => (
            <div key={u.seq}>
              {u.round !== visible[i - 1]?.round && <div className={styles.roundDiv}>{u.round}라운드</div>}
              {u.kind === 'judge' ? (
                <JudgeBubble
                  text={u.text}
                  yieldChanges={u.yieldChanges}
                  proposal={u.slot ? slotText(u.slot) : undefined}
                  isNew={playing && i === shown - 1}
                />
              ) : (
                <AgentBubble utterance={u} isMine={u.speakerId === viewerId} isNew={playing && i === shown - 1} />
              )}
            </div>
          ))}
        </div>
        {!playing && total > 0 && (
          <div className={styles.replay}>
            <button type="button" className="link" onClick={() => setShown(0)}>
              처음부터 다시 보기
            </button>
          </div>
        )}
      </section>

      {status === 'running' && (
        <div className={styles.waitCard}>
          <img className={styles.waitArt} src="/splash/peek.webp" alt="" aria-hidden="true" />
          <p className={styles.waitSay}>
            <b>조금만 기다려 주세요!</b>
            팀원들의 일정과 선호를 반영해 가장 알맞은 시간을 정리하고 있어요.
          </p>
        </div>
      )}
      <div ref={endRef} />
    </Screen>
  )
}

// 상태 카드: 지금 상태 + 라운드 칩 + 세 단계 바 + 조율 조건(길이·기간·방식)
function StatusCard({ scheduling: s, status, round }: { scheduling: Scheduling; status: SchedulingStatus; round: number }) {
  // 단계: 조율이 열렸으면 일정 수집은 끝났다. 도는 동안은 2단계, 끝나면 3단계까지. 못 잡으면 2단계에서 멈춘다
  const at = status === 'running' || status === 'failed' ? 1 : 2
  const finished = status === 'agreed' || status === 'settled'

  return (
    <section className={`sec ${styles.statusCard}`}>
      <div className={styles.statusHead}>
        {status === 'running' ? (
          <span className={styles.spin} aria-hidden="true" />
        ) : (
          <span className={styles.endDot} data-status={status} aria-hidden="true">
            <Icon name={status === 'failed' ? 'alert' : 'check'} />
          </span>
        )}
        <div className={styles.statusText}>
          <b className={styles.statusTitle}>{STATUS[status].title}</b>
          <p className="meta">{s.topic}</p>
        </div>
        <span className={`${styles.roundChip} num`}>
          {Math.min(round, MAX_ROUNDS)} / {MAX_ROUNDS} 라운드
        </span>
      </div>

      <ol className={styles.stages} aria-label="조율 단계">
        {STAGES.map((label, i) => {
          const state = i < at || (finished && i === at) ? 'done' : i === at ? (status === 'failed' ? 'fail' : 'now') : 'todo'
          return (
            <li key={label} data-state={state}>
              <span className={styles.dot}>{state === 'done' && <Icon name="check" small />}</span>
              <span className={styles.stageLabel}>{label}</span>
            </li>
          )
        })}
      </ol>

      <div className={styles.chips}>
        <span>{formatDuration(s.durationMin)}</span>
        <span className="num">{formatRange(s.windowStart, s.windowEnd)}</span>
        <span>{s.mode === '상관없음' ? '대면 · 비대면 상관없음' : s.mode}</span>
      </div>
    </section>
  )
}

type RoundState = 'done' | 'now' | 'todo' | 'skip'

// 조율 진행 상황: 라운드마다 한 줄 요약. 그 라운드에 판단 에이전트가 낸 시간과 거절 수로 쓴다
function RoundTimeline({
  utterances,
  status,
  round,
  roundsUsed,
}: {
  utterances: Utterance[]
  status: SchedulingStatus
  round: number
  roundsUsed: number
}) {
  const rows = Array.from({ length: MAX_ROUNDS }, (_, i) => {
    const r = i + 1
    const said = utterances.filter((u) => u.round === r)
    const pick = said.find((u) => u.kind === 'judge' && u.slot)?.slot ?? null
    const rejects = said.filter((u) => u.kind === 'answer' && u.answer === '거절').length
    const answers = said.filter((u) => u.kind === 'answer').length

    let state: RoundState
    if (status === 'running') state = r < round ? 'done' : r === round ? 'now' : 'todo'
    else state = r <= Math.max(roundsUsed, round) ? 'done' : 'skip'

    let line: string
    if (state === 'todo') line = r === MAX_ROUNDS ? '마지막 라운드 · 필요하면 판단 에이전트가 정해요' : '기다리는 중'
    else if (state === 'skip') line = '앞에서 정해져 필요 없었어요'
    else if (!pick) line = '각자 원하는 시간을 어필하는 중'
    else if (answers === 0) line = `${slotShort(pick)} 제안 · 응답을 받는 중`
    else line = `${slotShort(pick)} 제안 · ${rejects > 0 ? `${rejects}명 거절` : '모두 수락'}`

    return { r, state, line }
  })

  return (
    <section className={`sec ${styles.timeline}`}>
      <h2 className={styles.cardTitle}>
        <span className={styles.titleIcon} aria-hidden="true">
          ☰
        </span>
        조율 진행 상황
      </h2>
      <ol className={styles.rounds}>
        {rows.map(({ r, state, line }) => (
          <li key={r} data-state={state}>
            <span className={styles.rdot}>{state === 'done' && <Icon name="check" small />}</span>
            <div>
              <b className={styles.rname}>
                {r}라운드 {state === 'now' && <span className={styles.nowTag}>(진행 중)</span>}
              </b>
              <p className={`meta ${styles.rline}`}>{line}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}

const slotShort = (slot: Slot) => `${formatSlot(slot.startAt, slot.endAt)}`

type DockProps = {
  scheduling: Scheduling
  status: SchedulingStatus
  round: number
  slot: Slot | null
  isLeader: boolean
}

// 하단: 도는 동안은 한 줄, 끝나면 확정 카드(→ 조율 결과), 못 잡으면 다시 조율
function Dock({ scheduling: s, status, round, slot, isLeader }: DockProps) {
  const badge = <Badge tone={STATUS[status].tone}>{STATUS[status].label}</Badge>

  if (status === 'running') {
    return (
      <p className={styles.sum}>
        {badge} <span className="meta num">{round}라운드 진행 중 · 최대 {MAX_ROUNDS}</span>
      </p>
    )
  }

  if (status === 'failed') {
    return (
      <>
        <div className={styles.sum}>
          {badge} <span className="meta">기간 안에 모두가 될 수 있는 시간이 없어요</span>
          <p className="meta">{isLeader ? '기간을 넓혀 다시 조율해 주세요.' : '팀장이 기간을 넓혀 다시 조율할 거예요.'}</p>
        </div>
        {isLeader && (
          <div className="btn-row">
            <Link to={PATHS.schedulingNew} className="btn primary">
              기간 넓혀 다시 조율
            </Link>
          </div>
        )}
      </>
    )
  }

  const body = (
    <>
      <span className={styles.doneIcon} aria-hidden="true">
        <Icon name="calendar" />
      </span>
      <span className={styles.doneText}>
        <span className={styles.doneBadge}>
          <Icon name="check" small /> {status === 'agreed' ? '회의 합의' : '회의 확정'}
        </span>
        {slot ? (
          <b className={`${styles.when} num`}>
            {formatMonthDay(slot.startAt)} ({weekday(slot.startAt)}) {formatTimeRange(slot.startAt, slot.endAt)}
          </b>
        ) : (
          <b className={styles.when}>시간을 정했어요</b>
        )}
        <span className="meta num">
          {slot?.mode ?? ''} · {s.roundsUsed}라운드{status === 'agreed' ? '에서 합의 · 팀원 수락을 기다려요' : ' 뒤 판단 에이전트가 정함'}
        </span>
      </span>
      {s.proposalId && (
        <span className={styles.go} aria-hidden="true">
          <Icon name="back" />
        </span>
      )}
    </>
  )

  return s.proposalId ? (
    <Link to={pathTo.proposal(s.proposalId)} className={styles.doneCard} aria-label="조율 결과 확인하기">
      {body}
    </Link>
  ) : (
    <div className={styles.doneCard}>{body}</div>
  )
}
