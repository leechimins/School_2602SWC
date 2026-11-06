import dayjs from 'dayjs'
import type { Id, IsoDateTime } from '../types/common.ts'
import type { SuggestionPatch } from '../types/meeting.ts'
import type { TaskInput, TaskStatus } from '../types/task.ts'
import { SEED, type DemoState, type SeedTask } from './seed.ts'

// 액션 표: 목 데이터를 바꾸는 동작을 모두 여기 모은다.
// 화면은 api/ 함수를 부르고, 목 모드의 api 함수가 dispatch(액션)을 보낸다.
// 실서버로 바꾸면 같은 동작을 서버가 하므로, 이 표는 서버 API 목록과 1:1로 맞춘다.
export type Action =
  | { type: 'clock/move'; minutes: number }
  | { type: 'clock/reset' }
  | { type: 'task/add'; input: TaskInput }
  | { type: 'task/edit'; taskId: Id; patch: Partial<TaskInput> }
  | { type: 'task/status'; taskId: Id; status: TaskStatus; reason: string | null }
  | { type: 'task/dismiss'; taskId: Id }
  | { type: 'suggestion/edit'; suggestionId: Id; patch: SuggestionPatch }
  | { type: 'suggestion/dismiss'; suggestionId: Id }
  | { type: 'suggestion/confirm'; suggestionIds: Id[]; by: Id }
  | { type: 'proposal/respond'; meetingId: Id; userId: Id; accept: boolean; feedback: string | null }
  | { type: 'notice/read'; userId: Id; noticeIds: Id[] }
  | { type: 'meeting/transcript'; meetingId: Id; text: string }

const now = (s: DemoState): IsoDateTime => s.clockNow

const updateTask = (s: DemoState, id: Id, fn: (t: SeedTask) => SeedTask): DemoState => ({
  ...s,
  tasks: s.tasks.map((t) => (t.id === id ? fn(t) : t)),
})

export function reduce(s: DemoState, action: Action): DemoState {
  switch (action.type) {
    case 'clock/move':
      return { ...s, clockNow: dayjs(s.clockNow).add(action.minutes, 'minute').format() }

    case 'clock/reset':
      return { ...s, clockNow: SEED.clockNow }

    case 'task/add': {
      const id = `t${s.nextSeq}`
      const added: SeedTask = {
        id,
        ...action.input,
        status: '시작 전',
        blockedReason: null,
        meetingId: null, // 출처 "직접 추가"
        confirmedBy: null,
        doneAt: null,
        dismissed: false,
      }
      return { ...s, tasks: [...s.tasks, added], nextSeq: s.nextSeq + 1 }
    }

    case 'task/edit':
      return updateTask(s, action.taskId, (t) => ({ ...t, ...action.patch }))

    case 'task/status':
      return updateTask(s, action.taskId, (t) => ({
        ...t,
        status: action.status,
        blockedReason: action.status === '막힘' ? action.reason : null,
        doneAt: action.status === '완료' ? now(s) : null, // 완료로 바뀐 때 완료 알림이 생긴다
      }))

    case 'task/dismiss':
      return updateTask(s, action.taskId, (t) => ({ ...t, dismissed: true }))

    case 'suggestion/edit':
      return {
        ...s,
        suggestions: s.suggestions.map((g) => (g.id === action.suggestionId ? { ...g, ...action.patch } : g)),
      }

    case 'suggestion/dismiss':
      return { ...s, suggestions: s.suggestions.filter((g) => g.id !== action.suggestionId) }

    case 'suggestion/confirm': {
      // 확정하면 "AI 제안" 표시가 사라지고 할 일 탭에 들어간다. 담당자가 없어도 확정된다
      const picked = s.suggestions.filter((g) => action.suggestionIds.includes(g.id))
      const confirmed: SeedTask[] = picked.map((g, i) => ({
        id: `t${s.nextSeq + i}`,
        title: g.title,
        dueDate: g.dueDate,
        assigneeId: g.assigneeId,
        status: '시작 전',
        blockedReason: null,
        meetingId: g.meetingId,
        confirmedBy: action.by,
        doneAt: null,
        dismissed: false,
      }))
      return {
        ...s,
        tasks: [...s.tasks, ...confirmed],
        suggestions: s.suggestions.filter((g) => !action.suggestionIds.includes(g.id)),
        nextSeq: s.nextSeq + picked.length,
      }
    }

    case 'proposal/respond': {
      const proposals = s.proposals.map((p) => {
        if (p.meetingId !== action.meetingId) return p
        const feedback = action.feedback ? { ...p.feedback, [action.userId]: action.feedback } : p.feedback
        if (p.settled) return { ...p, feedback } // 조정안은 피드백 한 줄만 받는다
        return { ...p, feedback, responses: { ...p.responses, [action.userId]: action.accept ? '수락' : '거절' } as const }
      })
      // 응답할 사람이 모두 수락하면 회의가 자동으로 확정된다
      const p = proposals.find((x) => x.meetingId === action.meetingId)
      const allAccepted = p ? Object.values(p.responses).every((r) => r === '수락') : false
      return {
        ...s,
        proposals,
        meetings: s.meetings.map((m) =>
          m.id === action.meetingId && allAccepted ? { ...m, status: 'confirmed' } : m,
        ),
      }
    }

    case 'notice/read': {
      const before = s.readNotices[action.userId] ?? []
      const merged = [...new Set([...before, ...action.noticeIds])]
      return { ...s, readNotices: { ...s.readNotices, [action.userId]: merged } }
    }

    case 'meeting/transcript': {
      const lines = action.text
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
        .map((text) => ({ speakerId: null, text }))
      return {
        ...s,
        meetings: s.meetings.map((m) => (m.id === action.meetingId ? { ...m, transcript: lines } : m)),
      }
    }
  }
}
