import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { getScheduling } from '../api/scheduling.ts'
import AgentBubble from '../components/AgentBubble.tsx'
import Badge from '../components/Badge.tsx'
import JudgeBubble from '../components/JudgeBubble.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import Waiting from '../components/Waiting.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { formatDuration, formatRange, formatSlot } from '../lib/date.ts'
import { PATHS, pathTo } from '../lib/paths.ts'
import { UTTERANCE_MS, later } from '../lib/timers.ts'
import type { Tone } from '../lib/tones.ts'
import type { Id } from '../types/common.ts'
import type { Scheduling, SchedulingStatus, Slot, Utterance } from '../types/scheduling.ts'
import styles from './SchedulingPage.module.css'

const MAX_ROUNDS = 3

const STATUS: Record<SchedulingStatus, { label: string; tone: Tone; title: string }> = {
  running: { label: '진행 중', tone: 'plain', title: '시간 정하는 중' },
  agreed: { label: '합의', tone: 'ok', title: '시간을 정했어요' },
  settled: { label: '조정', tone: 'warn', title: '판단 에이전트가 정했어요' },
  failed: { label: '못 잡음', tone: 'danger', title: '시간을 못 잡았어요' },
}

const slotText = (slot: Slot) => `${formatSlot(slot.startAt, slot.endAt)} · ${slot.mode}`

// 사람이 회의안을 거절해서 다시 시작한 라운드들. 앞 라운드에서 개인 에이전트가 모두 수락(합의)했는데
// 다음 라운드가 있으면 그 사이에 사람이 거절한 것이다. 누가 거절했는지는 서버도 주지 않고 화면도 말하지 않는다
function rerunRounds(utterances: Utterance[]): Set<number> {
  const out = new Set<number>()
  for (const u of utterances) {
    const prev = utterances.filter((x) => x.round === u.round - 1 && x.kind === 'answer')
    if (prev.length > 0 && prev.every((x) => x.answer === '수락')) out.add(u.round)
  }
  return out
}

// 시간 정하는 과정: 왜 이 시간이 나왔는지 대화로 보여 준다. 앱에서 가장 중요한 화면이다.
// 라운드마다 개인 에이전트 어필 → 판단 에이전트가 하나를 고름 → 개인 에이전트 수락·거절. 에이전트가 모두 수락하면 사람이 수락·거절한다
// 발언 목록을 한 번에 받아 1.6초마다 하나씩 쌓는다. 스피너로 덮지 않고, 라운드 표시가 같이 오른다.
export default function SchedulingPage() {
  const { schedulingId } = useParams()
  const user = useCurrentUser()
  const res = useApi(() => getScheduling(user.roomId, schedulingId ?? ''), [user.roomId, user.id, schedulingId])

  // 조율은 서버 뒷단에서 돈다. 도는 동안 발언 간격마다 다시 불러, 새로 쌓인 발언을 Talk가 이어서 재생한다
  const running = res.status === 'ready' && res.data.status === 'running'
  const { reload } = res
  useEffect(() => {
    if (!running) return
    return later(reload, UTTERANCE_MS)
  }, [running, reload, res])

  if (!schedulingId) return <Navigate to={PATHS.home} replace />
  if (res.status === 'ready') {
    return <Talk key={res.data.id} scheduling={res.data} viewerId={user.id} isLeader={user.isLeader} />
  }
  return (
    <Screen title="회의 잡기" backTo={PATHS.home}>
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
    if (shown > 0) endRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
  }, [shown])

  const visible = s.utterances.slice(0, shown)
  const round = visible.at(-1)?.round ?? 1
  // 말이 다 나왔어도 서버가 아직 정리 중이면 진행 중으로 둔다
  const status: SchedulingStatus = playing ? 'running' : s.status
  const lastSlot = s.utterances.findLast((u) => u.slot)?.slot ?? null
  const reruns = rerunRounds(s.utterances)
  // 거절 뒤 다시 조율하는 중에 처음부터 재생되면, 이미 본 앞 라운드를 건너뛰고 마지막으로 다시 시작한 곳부터 볼 수 있다
  const skipTo = reruns.size > 0 ? s.utterances.findIndex((u) => u.round === Math.max(...reruns)) : -1
  const skip = playing && shown < skipTo ? () => setShown(skipTo) : undefined

  return (
    <Screen
      title="회의 잡기"
      backTo={PATHS.home}
      dock={<Dock scheduling={s} status={status} round={round} slot={lastSlot} isLeader={isLeader} onSkip={skip} />}
    >
      <div className={styles.head}>
        <p className={styles.topic}>
          {s.topic} <span className={styles.state}>{STATUS[status].title}</span>
        </p>
        <div className={styles.chips}>
          <span>{formatDuration(s.durationMin)}</span>
          <span className="num">{formatRange(s.windowStart, s.windowEnd)}</span>
          <span>{s.mode === '상관없음' ? '대면 · 비대면 상관없음' : s.mode}</span>
        </div>
        <div className={styles.rounds} role="img" aria-label={`최대 ${MAX_ROUNDS}라운드 중 ${round}라운드`}>
          {Array.from({ length: MAX_ROUNDS }, (_, i) => (
            <i key={i} className={i < round ? styles.on : undefined} />
          ))}
          <span className="num">
            {round} / 최대 {MAX_ROUNDS} 라운드
          </span>
        </div>
      </div>

      <div className={styles.talk} aria-live="polite">
        {visible.map((u, i) => (
          <div key={u.seq}>
            {u.round !== visible[i - 1]?.round && (
              <>
                <div className={styles.roundDiv}>
                  {u.round}라운드{reruns.has(u.round) && ' · 다시 조율'}
                </div>
                {reruns.has(u.round) && <p className={`meta ${styles.rerun}`}>팀원이 회의안을 거절해서, 그 시간을 빼고 다시 조율해요</p>}
              </>
            )}
            {u.kind === 'judge' ? (
              <JudgeBubble
                text={u.text}
                proposal={u.slot ? slotText(u.slot) : undefined}
                isNew={playing && i === shown - 1}
              />
            ) : (
              <AgentBubble utterance={u} isMine={u.speakerId === viewerId} isNew={playing && i === shown - 1} />
            )}
          </div>
        ))}
        <div ref={endRef} />
      </div>

      {!playing && total > 0 && (
        <div className={styles.replay}>
          <button type="button" className="link" onClick={() => setShown(0)}>
            처음부터 다시 보기
          </button>
        </div>
      )}
    </Screen>
  )
}

type DockProps = {
  scheduling: Scheduling
  status: SchedulingStatus
  round: number
  slot: Slot | null
  isLeader: boolean
  onSkip?: () => void // 거절 뒤 다시 조율한 라운드로 건너뛰기. 건너뛸 앞 라운드가 재생 중일 때만
}

// 하단: 지금 어디까지 왔는지 한 줄 + 끝나면 조율 결과로 가는 버튼
function Dock({ scheduling: s, status, round, slot, isLeader, onSkip }: DockProps) {
  const badge = <Badge tone={STATUS[status].tone}>{STATUS[status].label}</Badge>

  if (status === 'running') {
    return (
      <div className={`row-between ${styles.sum}`}>
        <p>
          {badge} <span className="meta num">{round}라운드 진행 중 · 최대 {MAX_ROUNDS}</span>
        </p>
        {onSkip && (
          <button type="button" className="link" onClick={onSkip}>
            다시 조율한 곳으로 건너뛰기
          </button>
        )}
      </div>
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

  return (
    <>
      <div className={styles.sum}>
        {badge}{' '}
        <span className="meta num">
          {s.roundsUsed}라운드{status === 'agreed' ? '에서 합의' : ' 뒤 판단 에이전트가 정함 · 그대로 확정돼요'}
        </span>
        {slot && <b className={`${styles.when} num`}>{slotText(slot)}</b>}
      </div>
      {s.proposalId && (
        <div className="btn-row">
          <Link to={pathTo.proposal(s.proposalId)} className="btn primary">
            조율 결과 확인하기
          </Link>
        </div>
      )}
    </>
  )
}
