import { useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { messageOf } from '../api/client.ts'
import { getProposal, respondProposal, undoFeedbackChange } from '../api/scheduling.ts'
import Avatar from '../components/Avatar.tsx'
import Badge from '../components/Badge.tsx'
import ConfirmSheet, { type ConfirmResult } from '../components/ConfirmSheet.tsx'
import JudgeBubble from '../components/JudgeBubble.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import YieldSteps from '../components/YieldSteps.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { formatDuration, formatSlot, minutesBetween } from '../lib/date.ts'
import { withJosa } from '../lib/korean.ts'
import { PATHS, pathTo } from '../lib/paths.ts'
import { BURDEN_LABEL, BURDEN_TONE } from '../lib/tones.ts'
import type { Id } from '../types/common.ts'
import type { Proposal, ResponseState } from '../types/scheduling.ts'
import styles from './ProposalPage.module.css'

const RESPONSE_TONE = { 대기: 'plain', 수락: 'ok', 거절: 'danger' } as const

// 회의 일정 조율 확인: 시간 → 부담(내 줄은 숫자, 다른 사람은 말로만) → 판단 근거 → 사람별 응답.
// 화면은 "결과 표시"와 "확정 방식(응답 영역)"으로 나뉜다.
//   합의안: 사람이 수락·거절하고, 전원 수락하면 자동 확정
//   조정안: 판단 에이전트가 바로 확정했으므로 피드백 한 줄만 받는다
export default function ProposalPage() {
  const { proposalId } = useParams()
  const user = useCurrentUser()
  const res = useApi(() => getProposal(user.roomId, proposalId ?? ''), [user.roomId, user.id, proposalId])

  if (!proposalId) return <Navigate to={PATHS.home} replace />
  if (res.status !== 'ready') {
    return (
      <Screen title="회의 일정" backTo={PATHS.home}>
        {res.status === 'error' && <RetryBox message={res.message} onRetry={res.reload} />}
      </Screen>
    )
  }

  const p = res.data
  // 조율 없이 "지금 회의 기록하기"로 만든 회의는 회의안이 없다(응답할 사람 0명). 회의록 화면으로 보낸다
  if (p.schedulingId === null && p.responders.length === 0) return <Navigate to={pathTo.meeting(p.id)} replace />
  return (
    <Screen title="회의 일정" backTo={PATHS.home} dock={<RespondDock proposal={p} roomId={user.roomId} />}>
      <ResultSummary proposal={p} />
      <Burdens proposal={p} viewerId={user.id} />
      <div className={styles.judge}>
        <JudgeBubble text={p.rationale}>
          <YieldGetterBox proposal={p} />
        </JudgeBubble>
      </div>
      <Responses proposal={p} viewerId={user.id} />
      {p.feedbackOnly && !p.myFeedback && <SettledFeedback proposal={p} roomId={user.roomId} />}
      {p.myFeedback && <MyFeedbackCard proposal={p} />}
      {p.schedulingId && (
        <div className={styles.center}>
          <Link to={pathTo.scheduling(p.schedulingId)} className="link">
            조율 과정 다시 보기
          </Link>
        </div>
      )}
    </Screen>
  )
}

// ── 결과 표시 ───────────────────────────────────────────

// 합의안이 보통이라 따로 표시하지 않고, 판단 에이전트가 정한 조정안만 뱃지와 한 줄로 알린다
function ResultSummary({ proposal: p }: { proposal: Proposal }) {
  return (
    <section className="sec">
      <div className="row-between">
        <span>
          {p.settled && (
            <>
              <Badge tone="warn">조정</Badge>{' '}
              <span className="meta num">{p.roundsUsed ? `${p.roundsUsed}라운드 뒤 ` : ''}판단 에이전트가 정함</span>
            </>
          )}
        </span>
        <Badge tone={p.confirmed ? 'ok' : p.cancelled ? 'danger' : 'warn'}>{p.confirmed ? '확정' : p.cancelled ? '취소' : '확정 대기'}</Badge>
      </div>
      <b className={`${styles.big} num`}>{formatSlot(p.startAt, p.endAt)}</b>
      <p className="meta">
        <span className={styles.mode}>{p.mode}</span> · {formatDuration(minutesBetween(p.startAt, p.endAt))} · {p.topic}
      </p>
      {p.absentName && <p className="meta">{p.absentName} 빠짐 · 회의록 요약을 따로 보내요</p>}
      {p.confirmed && !p.settled && <p className="meta">{p.absentName ? '빠진 사람 말고 모두' : '모두'} 수락해서 회의가 확정됐어요</p>}
      {p.cancelled && <p className="meta">누군가 거절해서 이 시간은 취소됐어요. 남은 라운드로 다시 조율해요</p>}
    </section>
  )
}

// 부담: 내 줄이 맨 위(불편 점수는 본인에게만 숫자로), 다른 사람은 말로만.
// 불참안에서 빠진 사람은 점수 대신 빠진다는 한 줄(목업 버그 ③)
function Burdens({ proposal: p, viewerId }: { proposal: Proposal; viewerId: Id }) {
  const others = p.responders.filter((r) => r.userId !== viewerId)
  return (
    <section className="sec">
      <h2>부담</h2>
      <div className={styles.mine}>
        {p.myScore === null ? (
          <p className="strong">이번 회의에서 빠져요 · 회의록 요약을 따로 보내 드려요</p>
        ) : (
          <p className="strong">
            내 불편 <span className="num">{p.myScore}/5</span> · {p.myReason}
          </p>
        )}
        <span className="meta">나만 보여요</span>
      </div>
      {others.map((r) => (
        <div key={r.userId} className={styles.other}>
          <Avatar name={r.name} />
          <span className="strong">{r.name}</span>
          <Badge tone={BURDEN_TONE[r.burden]}>{BURDEN_LABEL[r.burden]}</Badge>
          <span className="meta">{r.reason}</span>
        </div>
      ))}
    </section>
  )
}

// 이번에 양보 점수를 받는 사람: 누적은 단계로만, 내가 받을 때만 숫자와 근거 한 줄
function YieldGetterBox({ proposal: p }: { proposal: Proposal }) {
  const g = p.yieldGetter
  if (!g) return null
  const name = g.isMe ? '나' : g.name
  return (
    <div className={styles.box}>
      <p className="meta">이번에 양보 점수 받는 사람</p>
      <div className={styles.yrow}>
        <b>
          {name}
          {g.isMe && <span className="num"> +{p.myYieldPoints}</span>}
        </b>
        <YieldSteps level={g.to} />
        <span>
          {g.from === g.to ? (
            <>
              <b>{g.to}</b> · 가장 높은 단계라 그대로
            </>
          ) : (
            <>
              {g.from} → <b>{g.to}</b>
            </>
          )}
        </span>
      </div>
      <p className="meta">
        {g.isMe ? (
          <>
            내 불편 <span className="num">{p.myScore}/5</span>만큼 맞춰 줘서 <span className="num">+{p.myYieldPoints}</span>이에요.
            조금 불편하면 +1, 많이 불편하면 +2를 받아요.
          </>
        ) : (
          `${withJosa(g.name, '은/는')} ${g.burden === '많이' ? '많이' : '조금'} 불편한 시간을 맞춰 줬어요. 불편한 만큼 양보 점수를 더 받아요.`
        )}
      </p>
    </div>
  )
}

function Responses({ proposal: p, viewerId }: { proposal: Proposal; viewerId: Id }) {
  // 조정안은 응답을 받지 않으므로 사람별 응답 줄이 없다
  if (p.feedbackOnly) return null
  const accepted = p.responders.filter((r) => r.state === '수락').length
  return (
    <section className="sec">
      <h2 className={`${styles.flush} num`}>
        {p.responders.length}명 중 {accepted}명 수락
      </h2>
      <div className={styles.responses}>
        {p.responders.map((r) => (
          <div key={r.userId}>
            <Avatar name={r.name} size="large" />
            <span>
              {r.name}
              {r.userId === viewerId && ' (나)'}
            </span>
            <Badge tone={RESPONSE_TONE[r.state]}>{r.state}</Badge>
          </div>
        ))}
      </div>
    </section>
  )
}

// 내가 남긴 한 줄과 반영 결과. 선호가 바뀌었으면 무엇이 바뀌었는지 보여 주고 되돌릴 수 있다
function MyFeedbackCard({ proposal: p }: { proposal: Proposal }) {
  const f = p.myFeedback
  if (!f) return null
  return (
    <section className="sec">
      <p className="strong">“{f.text}”</p>
      {!f.change ? (
        <p className="meta">시간 얘기는 아니라서 선호는 그대로 뒀어요.</p>
      ) : (
        <div className="row-between">
          <span className="meta">{f.undone ? '되돌렸어요. 선호는 그대로예요.' : f.change}</span>
          {!f.undone && (
            <button type="button" className="link" onClick={() => undoFeedbackChange(p.id)}>
              되돌리기
            </button>
          )}
        </div>
      )}
    </section>
  )
}

// ── 확정 방식(응답 영역) ─────────────────────────────────

// 조정안: 이미 확정이라 수락·거절 창 없이 피드백 칸이 화면에 바로 보인다
function SettledFeedback({ proposal: p, roomId }: { proposal: Proposal; roomId: Id }) {
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const send = () =>
    respondProposal(roomId, p.id, { accept: true, feedback: text.trim() || null }).catch((e: unknown) => setError(messageOf(e)))

  return (
    <section className="sec">
      <p className="strong">이 시간으로 정해졌어요. 한 줄 남기시겠어요?</p>
      <p className="meta">내 에이전트가 다음 회의부터 참고해요. 비워 둬도 돼요.</p>
      <div className={styles.inline}>
        <input
          className="field"
          value={text}
          maxLength={40}
          placeholder="예: 금요일은 역시 힘드네요"
          aria-label="이 시간 어때요"
          onChange={(e) => setText(e.target.value)}
        />
        <button type="button" className="btn small" disabled={!text.trim()} onClick={send}>
          남기기
        </button>
      </div>
      {error && <p className="meta">{error}</p>}
    </section>
  )
}

type Asking = 'accept' | 'reject' | null

// 합의안: 거절(글자) | 수락(버튼). 누르면 한 줄을 받는 창이 뜨고, 전원이 수락하면 따로 누르지 않아도 확정된다
function RespondDock({ proposal: p, roomId }: { proposal: Proposal; roomId: Id }) {
  const [asking, setAsking] = useState<Asking>(null)
  const [error, setError] = useState<string | null>(null)

  if (p.feedbackOnly || p.confirmed || p.myState === null) return null

  const respond = async (accept: boolean, { ok, value }: ConfirmResult) => {
    setAsking(null)
    if (!ok) return
    try {
      await respondProposal(roomId, p.id, { accept, feedback: value || null })
    } catch (e) {
      setError(messageOf(e))
    }
  }

  return (
    <>
      {error && <p className="meta">{error}</p>}
      <DockBody proposal={p} state={p.myState} onAsk={setAsking} />
      {asking === 'accept' && (
        <ConfirmSheet
          title="이 시간으로 수락할까요?"
          body="이 시간이 어떤지 한 줄 남기면 내 에이전트가 다음 회의부터 참고해요. 비워 둬도 돼요."
          okLabel="수락하기"
          irreversible={false}
          input={{ label: '이 시간 어때요', placeholder: '예: 수업 바로 뒤라 조금 빠듯해요' }}
          onClose={(r) => respond(true, r)}
        />
      )}
      {asking === 'reject' && (
        <ConfirmSheet
          title="조율 결과를 거절할까요?"
          body="이유를 한 줄 남기면 판단 에이전트가 다음 라운드에 반영하고, 내 에이전트도 다음 회의부터 참고해요. 비워 둬도 돼요."
          okLabel="거절하기"
          irreversible={false}
          input={{ label: '거절 이유', placeholder: '예: 금요일은 역시 힘들어요' }}
          onClose={(r) => respond(false, r)}
        />
      )}
    </>
  )
}

type DockBodyProps = { proposal: Proposal; state: ResponseState; onAsk: (a: Asking) => void }

function DockBody({ proposal: p, state, onAsk }: DockBodyProps) {
  if (state === '대기') {
    return (
      <div className="btn-row">
        <button type="button" className="btn quiet" onClick={() => onAsk('reject')}>
          거절
        </button>
        <button type="button" className="btn primary" onClick={() => onAsk('accept')}>
          수락
        </button>
      </div>
    )
  }
  // 거절: 라운드가 남았으면 서버가 바로 다시 조율하고(회의 취소), 3라운드를 다 썼으면 나를 불참으로 두고 나머지 응답을 기다린다
  if (state === '거절' && p.cancelled) {
    return (
      <>
        <p className="meta">거절을 전달했어요. 남은 라운드로 다시 조율하고 있어요.</p>
        {p.schedulingId && (
          <div className="btn-row">
            <Link to={pathTo.scheduling(p.schedulingId)} className="btn primary">
              다시 조율하는 과정 보기
            </Link>
          </div>
        )}
      </>
    )
  }
  if (state === '거절') {
    return <p className="meta">거절을 전달했어요. 3라운드를 다 써서 다시 조율하지 않고, 이번 회의는 불참으로 둬요.</p>
  }
  const waiting = p.responders.filter((r) => r.state === '대기').map((r) => r.name)
  return <p className="meta">수락했어요. {waiting.join(', ')}의 응답을 기다리는 중이에요.</p>
}
