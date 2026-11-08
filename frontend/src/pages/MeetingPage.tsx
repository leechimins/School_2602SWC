import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { confirmSuggestions, dismissSuggestion, editSuggestion, getMeeting } from '../api/records.ts'
import { getRoom } from '../api/rooms.ts'
import { addTask, changeTaskStatus, dismissTask, keepTask } from '../api/tasks.ts'
import AddTaskCard from '../components/AddTaskCard.tsx'
import Badge from '../components/Badge.tsx'
import ConfirmSheet from '../components/ConfirmSheet.tsx'
import EmptyState from '../components/EmptyState.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import SuggestionCard from '../components/SuggestionCard.tsx'
import TaskRow from '../components/TaskRow.tsx'
import UnneededCard from '../components/UnneededCard.tsx'
import Waiting from '../components/Waiting.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { useSummarize } from '../hooks/useSummarize.ts'
import { formatDayLabel, formatMD, formatTimeRange } from '../lib/date.ts'
import { PATHS, pathTo } from '../lib/paths.ts'
import type { MeetingDetail, Minutes } from '../types/meeting.ts'
import type { Member } from '../types/room.ts'
import styles from './MeetingPage.module.css'

// 회의록: 주제 한 줄 → 원문(펼쳐 보기) → 요약(결정·논의·보류) → 회의에서 끝난 일 → 업무 배정 검토(할 일 제안) → 필요 없어 보이는 일.
// 할 일 제안은 여기서만 보이고, 확정해야 할 일 탭에 들어간다.
export default function MeetingPage() {
  const { meetingId = '' } = useParams()
  const user = useCurrentUser()
  const res = useApi(() => getMeeting(user.roomId, meetingId), [user.roomId, user.id, meetingId])
  const room = useApi(() => getRoom(user.roomId), [user.roomId, user.id])
  const members = room.status === 'ready' ? room.data.members : []

  return (
    <Screen title="회의록" backTo={PATHS.schedule}>
      {res.status === 'error' && <RetryBox message={res.message} onRetry={res.reload} />}
      {res.status === 'ready' && <MeetingBody meeting={res.data} members={members} />}
    </Screen>
  )
}

function MeetingBody({ meeting: m, members }: { meeting: MeetingDetail; members: Member[] }) {
  const user = useCurrentUser()
  const [showRaw, setShowRaw] = useState(false)
  const recorded = m.transcript.length > 0

  return (
    <>
      <section className="sec">
        <p className={styles.topic}>{m.minutes?.headline ?? m.topic}</p>
        <p className={`${styles.metaRow} num`}>
          <span>{formatDayLabel(m.startAt)}</span>
          <span>{formatTimeRange(m.startAt, m.endAt)}</span>
          <span>{m.mode}</span>
          <span>참석 {m.attendees.join(' · ')}</span>
        </p>
        {recorded && (
          <button type="button" className="btn small block" aria-expanded={showRaw} onClick={() => setShowRaw(!showRaw)}>
            {showRaw ? '원문 접기' : `원문 전체 보기 (${m.transcript.length}줄)`}
          </button>
        )}
        {showRaw && (
          <ol className={styles.lines}>
            {m.transcript.map((line) => (
              <li key={line.seq} className={styles.line}>
                <b>{line.speakerName ?? '—'}</b>
                <span>{line.text}</span>
              </li>
            ))}
          </ol>
        )}
      </section>

      {!recorded ? (
        <section className="sec">
          <EmptyState
            title="아직 기록이 없어요"
            description="받아적거나 직접 쓰면 에이전트가 요약하고 할 일을 뽑아 제안해요."
            action={{ label: '회의 기록하기', to: pathTo.record(m.id) }}
          />
        </section>
      ) : m.minutes ? (
        <MinutesCard minutes={m.minutes} />
      ) : (
        <SummarizeCard meetingId={m.id} />
      )}

      {m.doneTasks.length > 0 && (
        <>
          <div className="sec-h">
            <h2>회의에서 끝난 일</h2>
            <span className="meta">직접 체크 안 해도 돼요</span>
          </div>
          <section className="sec">
            <ul className={styles.list}>
              {m.doneTasks.map((task) => (
                <TaskRow
                  key={task.id}
                  task={task}
                  meetingDone
                  onStatusChange={(t, status, reason) => changeTaskStatus(user.roomId, t.id, status, reason)}
                />
              ))}
            </ul>
          </section>
        </>
      )}

      {m.minutes && <Review meeting={m} members={members} />}
    </>
  )
}

const MINUTE_GROUPS = [
  ['결정', 'decisions'],
  ['논의', 'discussions'],
  ['보류', 'pendings'],
] as const

function MinutesCard({ minutes }: { minutes: Minutes }) {
  const groups = MINUTE_GROUPS.filter(([, key]) => minutes[key].length > 0)
  if (groups.length === 0) return null
  return (
    <section className="sec">
      {groups.map(([label, key]) => (
        <div key={key} className={styles.group}>
          <b>{label}</b>
          {minutes[key].map((item) => (
            <p key={item} className={styles.item}>
              {item}
            </p>
          ))}
        </div>
      ))}
    </section>
  )
}

// 원문은 있는데 아직 정리 전이거나 정리가 실패한 회의. 원문은 위에 그대로 있다
function SummarizeCard({ meetingId }: { meetingId: string }) {
  const user = useCurrentUser()
  const { phase, run } = useSummarize(user.roomId, meetingId)
  if (phase === 'working') {
    return (
      <section className="sec">
        <Waiting what="회의록을 정리하고 할 일을 뽑는 중이에요" detail="원문은 먼저 저장했어요. 위에서 펼쳐 볼 수 있어요." />
      </section>
    )
  }
  return (
    <section className="sec">
      {phase === 'failed' ? (
        <>
          <Badge tone="warn">정리 못 함</Badge>
          <p className="strong">잠시 후 다시 해 주세요.</p>
          <p className="meta">원문은 저장했어요. 다시 하면 그 원문으로 정리해요.</p>
        </>
      ) : (
        <p className="meta">원문을 저장했어요. 정리하면 요약과 할 일 제안이 생겨요.</p>
      )}
      <button type="button" className="btn primary block" onClick={run}>
        {phase === 'failed' ? '다시 하기' : '정리하기'}
      </button>
    </section>
  )
}

// 업무 배정 검토: 확정 전 제안(고치기·삭제·하나씩/모두 확정) + 이미 확정한 것 + 직접 추가
function Review({ meeting: m, members }: { meeting: MeetingDetail; members: Member[] }) {
  const user = useCurrentUser()
  const [askingAll, setAskingAll] = useState(false)
  const pending = m.suggestions.length
  const total = pending + m.tasks.length
  const confirm = (ids: string[]) => confirmSuggestions(user.roomId, ids)

  return (
    <>
      <div className={styles.reviewTop}>
        <div>
          <p className="strong">이 회의에서 나온 할 일 {total}개</p>
          {total > 0 && (
            <>
              <p className="meta num">
                확정 {m.tasks.length} · 확정 전 제안 {pending} — 확정해야 할 일 탭에 보여요
              </p>
              <div className={styles.bar} role="img" aria-label={`${total}개 중 ${m.tasks.length}개 확정`}>
                <i style={{ width: `${Math.round((m.tasks.length / total) * 100)}%` }} />
              </div>
            </>
          )}
        </div>
        {pending > 0 && (
          <button type="button" className="btn small primary" onClick={() => setAskingAll(true)}>
            모두 확정
          </button>
        )}
      </div>

      {total === 0 && (
        <section className="sec">
          <p className="meta">이 회의에서 뽑은 할 일이 없어요. 필요하면 아래에서 직접 추가하세요.</p>
        </section>
      )}
      {m.suggestions.map((g) => (
        <SuggestionCard
          key={g.id}
          suggestion={g}
          members={members}
          onEdit={(patch) => editSuggestion(user.roomId, g.id, patch)}
          onConfirm={() => confirm([g.id])}
          onDismiss={() => dismissSuggestion(user.roomId, g.id)}
        />
      ))}
      {m.tasks.map((t) => (
        <article key={t.id} className={styles.confirmed}>
          <div className={styles.confirmedHead}>
            <Badge tone="ok">{t.confirmedByName ? `확정 · ${t.confirmedByName}` : '확정'}</Badge>
            <span className="strong">{t.title}</span>
          </div>
          <p className="meta num">
            {t.assigneeName ?? '담당자 없음'}
            {t.dueDate && ` · ${formatMD(t.dueDate)}까지`}
          </p>
        </article>
      ))}
      <AddTaskCard label="+ 직접 추가" members={members} onAdd={(input) => addTask(user.roomId, input, m.id)} />
      {m.unneededTasks.length > 0 && (
        <>
          <div className="sec-h">
            <h2>필요 없어 보이는 일</h2>
            <span className="meta">따로 확인해요</span>
          </div>
          {m.unneededTasks.map((item) => (
            <UnneededCard
              key={item.task.id}
              item={item}
              onKeep={() => keepTask(item.task.id)}
              onDelete={() => dismissTask(user.roomId, item.task.id)}
            />
          ))}
        </>
      )}
      {pending > 0 && (
        <p className={`meta ${styles.foot}`}>
          확정 전 제안은 할 일 탭에 보이지 않아요.
        </p>
      )}

      {askingAll && (
        <ConfirmSheet
          title={`할 일 ${pending}개를 모두 확정할까요?`}
          body="할 일 탭에 들어가요. 담당자가 없는 일은 '담당자 없음'으로 들어가요."
          okLabel="모두 확정"
          irreversible={false}
          onClose={({ ok }) => {
            setAskingAll(false)
            if (ok) confirm(m.suggestions.map((g) => g.id))
          }}
        />
      )}
    </>
  )
}
