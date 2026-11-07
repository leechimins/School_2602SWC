import type { Id, IsoDate } from '../types/common.ts'
import type { Member } from '../types/room.ts'

// 할 일 제안·직접 추가·고치기가 같이 쓰는 칸 두 개: 담당자 고르기, 기한 고르기.
// 담당자 없음은 오류가 아니라 정상인 시작 상태라 첫 칸에 둔다.

type AssigneeProps = {
  members: Member[]
  value: Id | null
  emptyLabel?: string // 비어 있을 때 글자: "담당자 없음" · "담당자 지정"
  className?: string
  onChange: (assigneeId: Id | null) => void
}

export function AssigneeSelect({ members, value, emptyLabel = '담당자 없음', className = '', onChange }: AssigneeProps) {
  return (
    <select
      className={`field ${className}`}
      aria-label="담당자"
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value || null)}
    >
      <option value="">{emptyLabel}</option>
      {members.map((m) => (
        <option key={m.id} value={m.id}>
          {m.name}
        </option>
      ))}
    </select>
  )
}

type DueProps = {
  value: IsoDate | null
  className?: string
  onChange: (dueDate: IsoDate | null) => void
}

export function DueInput({ value, className = '', onChange }: DueProps) {
  return (
    <input
      type="date"
      className={`field num ${className}`}
      aria-label="기한"
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value || null)}
    />
  )
}
