import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { getRoom } from '../api/rooms.ts'
import { addTask, changeTaskStatus, dismissTask, editTask, getTeamTasks } from '../api/tasks.ts'
import AddTaskCard from '../components/AddTaskCard.tsx'
import Avatar from '../components/Avatar.tsx'
import EmptyState from '../components/EmptyState.tsx'
import Icon, { type IconName } from '../components/Icon.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import TaskEditor from '../components/TaskEditor.tsx'
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

const FILTER_ICON: Partial<Record<Filter, IconName>> = { '진행 중': 'progress', 막힘: 'alert', 완료: 'check' }

// 할 일 탭(팀 할 일, 11/9 시안): 확정된 것만.
// 상태 칩(개수) → 확정 전 제안 안내 → 사람별 묶음(접기) → 목록 끝 "할 일 추가하기".
// "담당자 없음" 묶음은 회의 직후에 가장 크고, 정상인 상태라 오류색을 쓰지 않는다.
export default function TasksPage() {
  const user = useCurrentUser()
  const res = useApi(() => getTeamTasks(user.roomId), [user.roomId, user.id])
  const room = useApi(() => getRoom(user.roomId), [user.roomId, user.id])
  const members = room.status === 'ready' ? room.data.members : []
  const [adding, setAdding] = useState(false)
  const [filter, setFilter] = useState<Filter>('전체')

  const mine = (
    <Link to={PATHS.myTasks} className="link">
      내 할 일
    </Link>
  )
  // 목록 끝: 큰 "할 일 추가하기" 버튼 → 누르면 그 자리에 추가 카드
  const addArea = adding ? (
    <div className={styles.adding}>
      <AddTaskCard
        label="+ 할 일 추가"
        members={members}
        startOpen
        onClose={() => setAdding(false)}
        onAdd={(input) => addTask(user.roomId, input)}
      />
    </div>
  ) : (
    <button type="button" className={`btn primary ${styles.addBtn}`} onClick={() => setAdding(true)}>
      <Icon name="plus" /> 할 일 추가하기
    </button>
  )

  return (
    <Screen title="할 일" aux={mine} band={{ sub: '팀의 할 일을 한눈에 관리해요.' }}>
      {res.status === 'error' && <RetryBox message={res.message} onRetry={res.reload} />}
      {res.status === 'ready' && (
        <TeamTaskList data={res.data} members={members} addArea={addArea} filter={filter} setFilter={setFilter} />
      )}
    </Screen>
  )
}

type ListProps = {
  data: TeamTasks
  members: Member[]
  addArea: ReactNode
  filter: Filter
  setFilter: (f: Filter) => void
}

function TeamTaskList({ data, members, addArea, filter, setFilter }: ListProps) {
  const user = useCurrentUser()
  const [editingId, setEditingId] = useState<Id | null>(null)
  const [folded, setFolded] = useState<ReadonlySet<string>>(new Set())

  if (data.tasks.length === 0) {
    return (
      <>
        <section className="sec">
          <EmptyState
            title="아직 팀 할 일이 없어요"
            description="회의록에서 할 일 제안을 확정하면 사람별로 여기에 모여요. 회의와 상관없는 일은 아래 버튼으로 직접 추가해도 돼요."
            action={{ label: '일정으로 가기', to: PATHS.schedule }}
          />
        </section>
        {addArea}
      </>
    )
  }

  const list = data.tasks
    .filter((t) => filter === '전체' || t.status === filter)
    .sort((a, b) => Number(a.status === '완료') - Number(b.status === '완료')) // 기한 순(서버 정렬)은 유지하고 완료만 아래로
  // 묶음 순서: 담당자 없음 → 나 → 나머지 팀원
  const order: (Id | null)[] = [null, user.id, ...members.map((m) => m.id).filter((id) => id !== user.id)]
  const groups = order.map((id) => ({ id, tasks: list.filter((t) => t.assigneeId === id) })).filter((g) => g.tasks.length > 0)
  const nameOf = (id: Id | null) => (id ? (members.find((m) => m.id === id)?.name ?? '') : '담당자 없음')
  const toggle = (key: string) =>
    setFolded((prev) => {
      const next = new Set(prev)
      if (!next.delete(key)) next.add(key)
      return next
    })

  const rowOf = (task: Task) => (
    <TaskRow
      key={task.id}
      task={task}
      onStatusChange={(t, status: TaskStatus, reason) => changeTaskStatus(user.roomId, t.id, status, reason)}
      onEdit={task.canEdit ? (t) => setEditingId(t.id) : undefined}
      assign={{ members, onPick: (assigneeId) => editTask(user.roomId, task.id, { assigneeId }) }}
    >
      {editingId === task.id && (
        <TaskEditor
          task={task}
          members={members}
          onSave={(patch) => editTask(user.roomId, task.id, patch)}
          onDelete={() => dismissTask(user.roomId, task.id)}
          onClose={() => setEditingId(null)}
        />
      )}
    </TaskRow>
  )

  return (
    <>
      <div className={styles.chips} role="group" aria-label="상태로 거르기">
        {FILTERS.map((f) => {
          const icon = FILTER_ICON[f]
          return (
            <button key={f} type="button" aria-pressed={filter === f} data-tone={f} onClick={() => setFilter(f)}>
              {icon && <Icon name={icon} small />}
              {f}
              <span className={`${styles.chipN} num`}>
                {f === '전체' ? data.tasks.length : data.tasks.filter((t) => t.status === f).length}
              </span>
            </button>
          )
        })}
      </div>
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
      {groups.map((g) => {
        const key = g.id ?? 'none'
        const open = !folded.has(key)
        const name = nameOf(g.id)
        return (
          <div key={key} className={styles.group}>
            <button type="button" className={styles.groupHead} aria-expanded={open} onClick={() => toggle(key)}>
              {g.id ? <Avatar name={g.id === user.id ? '나' : name} size="large" /> : <span className={styles.noOne}>?</span>}
              <b className={styles.groupName}>
                {name}
                {g.id === user.id && ' (나)'}
              </b>
              <span className="meta num">{g.tasks.length}개</span>
              <span className={styles.fold} data-open={open}>
                <Icon name="chevron" small />
              </span>
            </button>
            {open && (
              <section className={`sec ${styles.groupCard}`}>
                <ul className={styles.list}>{g.tasks.map(rowOf)}</ul>
              </section>
            )}
          </div>
        )
      })}
      {list.length === 0 && (
        <section className="sec">
          <EmptyState title="조건에 맞는 할 일이 없어요" action={{ label: '전체 보기', onClick: () => setFilter('전체') }} />
        </section>
      )}
      {addArea}
    </>
  )
}
