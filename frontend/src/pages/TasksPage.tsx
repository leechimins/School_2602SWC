import { useState } from 'react'
import { Link } from 'react-router-dom'
import { getRoom } from '../api/rooms.ts'
import { addTask, changeTaskStatus, dismissTask, editTask, getTeamTasks } from '../api/tasks.ts'
import AddTaskCard from '../components/AddTaskCard.tsx'
import EmptyState from '../components/EmptyState.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import TaskEditor from '../components/TaskEditor.tsx'
import { AssigneeSelect } from '../components/TaskFields.tsx'
import TaskRow from '../components/TaskRow.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { PATHS } from '../lib/paths.ts'
import type { Id } from '../types/common.ts'
import type { Member } from '../types/room.ts'
import { TASK_STATUSES, type Task, type TaskStatus, type TeamTasks } from '../types/task.ts'
import styles from './TasksPage.module.css'

const FILTERS = ['전체', ...TASK_STATUSES] as const
type Filter = (typeof FILTERS)[number]

// 할 일 탭(팀 할 일): 확정된 것만. 사람별 남은 개수 → 확정 전 제안 안내 → 직접 추가 → 상태 필터 → 사람별 묶음.
// "담당자 없음" 묶음은 회의 직후에 가장 크고, 정상인 상태라 오류색을 쓰지 않는다.
export default function TasksPage() {
  const user = useCurrentUser()
  const res = useApi(() => getTeamTasks(user.roomId), [user.roomId, user.id])
  const room = useApi(() => getRoom(user.roomId), [user.roomId, user.id])
  const members = room.status === 'ready' ? room.data.members : []

  const mine = (
    <Link to={PATHS.myTasks} className={`link ${styles.aux}`}>
      내 할 일
    </Link>
  )

  return (
    <Screen title="할 일" aux={mine}>
      {res.status === 'error' && <RetryBox message={res.message} onRetry={res.reload} />}
      {res.status === 'ready' && <TeamTaskList data={res.data} members={members} />}
    </Screen>
  )
}

function TeamTaskList({ data, members }: { data: TeamTasks; members: Member[] }) {
  const user = useCurrentUser()
  const [filter, setFilter] = useState<Filter>('전체')
  const [editingId, setEditingId] = useState<Id | null>(null)
  const add = <AddTaskCard label="+ 할 일 추가" members={members} onAdd={(input) => addTask(user.roomId, input)} />

  if (data.tasks.length === 0) {
    return (
      <>
        <section className="sec">
          <EmptyState
            title="아직 팀 할 일이 없어요"
            description="회의록에서 할 일 제안을 확정하면 사람별로 여기에 모여요. 회의와 상관없는 일은 직접 추가해도 돼요."
            action={{ label: '일정으로 가기', to: PATHS.schedule }}
          />
        </section>
        {add}
      </>
    )
  }

  const max = Math.max(1, ...data.counts.map((c) => c.remaining))
  const list = data.tasks
    .filter((t) => filter === '전체' || t.status === filter)
    .sort((a, b) => Number(a.status === '완료') - Number(b.status === '완료')) // 기한 순(서버 정렬)은 유지하고 완료만 아래로
  // 묶음 순서: 담당자 없음 → 나 → 나머지 팀원
  const order: (Id | null)[] = [null, user.id, ...members.map((m) => m.id).filter((id) => id !== user.id)]
  const groups = order.map((id) => ({ id, tasks: list.filter((t) => t.assigneeId === id) })).filter((g) => g.tasks.length > 0)
  const nameOf = (id: Id | null) => (id ? (members.find((m) => m.id === id)?.name ?? '') : '담당자 없음')

  const rowOf = (task: Task) => (
    <TaskRow
      key={task.id}
      task={task}
      onStatusChange={(t, status: TaskStatus, reason) => changeTaskStatus(user.roomId, t.id, status, reason)}
      onEdit={task.canEdit ? (t) => setEditingId(t.id) : undefined}
    >
      {editingId === task.id ? (
        <TaskEditor
          task={task}
          members={members}
          onSave={(patch) => editTask(user.roomId, task.id, patch)}
          onDelete={() => dismissTask(user.roomId, task.id)}
          onClose={() => setEditingId(null)}
        />
      ) : (
        !task.assigneeId && (
          <div className={styles.assign}>
            <AssigneeSelect
              members={members}
              value={null}
              emptyLabel="담당자 지정"
              onChange={(assigneeId) => editTask(user.roomId, task.id, { assigneeId })}
            />
          </div>
        )
      )}
    </TaskRow>
  )

  return (
    <>
      <section className="sec">
        <h2>사람별 남은 할 일</h2>
        {data.counts.map((c) => (
          <div key={c.userId} className={styles.load}>
            <span>{c.name}</span>
            <span className={styles.bar}>
              <i style={{ width: `${Math.round((c.remaining / max) * 100)}%` }} />
            </span>
            <span className="meta num">{c.remaining}개</span>
          </div>
        ))}
      </section>
      {data.suggestionCount > 0 && (
        <div className={styles.hint}>
          <span>
            회의록에 확정 전 할 일 제안 <b className="num">{data.suggestionCount}</b>개가 있어요. 확정하면 여기에 들어와요.
          </span>
          <Link to={PATHS.schedule} className="link">
            일정
          </Link>
        </div>
      )}
      {add}
      <div className={styles.chips} role="group" aria-label="상태로 거르기">
        {FILTERS.map((f) => (
          <button key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)}>
            {f}
          </button>
        ))}
      </div>
      <p className={`meta ${styles.guide}`}>길게 누르거나 우클릭하면 고치기</p>
      {groups.map((g) => (
        <section key={g.id ?? 'none'} className="sec">
          <span className="cat">
            {nameOf(g.id)}
            {g.id === user.id && ' (나)'} <span className="n num">{g.tasks.length}</span>
          </span>
          <ul className={styles.list}>{g.tasks.map(rowOf)}</ul>
        </section>
      ))}
      {list.length === 0 && (
        <section className="sec">
          <EmptyState title="조건에 맞는 할 일이 없어요" action={{ label: '전체 보기', onClick: () => setFilter('전체') }} />
        </section>
      )}
    </>
  )
}
