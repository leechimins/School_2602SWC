import dayjs from 'dayjs'
import type { Id, IsoDateTime } from '../types/common.ts'
import { formatMonthDay } from '../lib/date.ts'
import type { SuggestionPatch } from '../types/meeting.ts'
import { YIELD_LEVELS, type RoomInput, type YieldLevel } from '../types/room.ts'
import type { SchedulingInput } from '../types/scheduling.ts'
import type { TaskInput, TaskStatus } from '../types/task.ts'
import { DEMO_SCENARIO, SEED, type DemoState, type SeedFeedback, type SeedTask } from './seed.ts'

// 액션 표: 목 데이터를 바꾸는 동작을 모두 여기 모은다.
// 화면은 api/ 함수를 부르고, 목 모드의 api 함수가 dispatch(액션)을 보낸다.
// 실서버로 바꾸면 같은 동작을 서버가 하므로, 이 표는 서버 API 목록과 1:1로 맞춘다.
export type Action =
  | { type: 'clock/move'; minutes: number }
  | { type: 'clock/reset' }
  | { type: 'room/create'; input: RoomInput }
  | { type: 'scheduling/start'; input: SchedulingInput }
  | { type: 'scheduling/finish'; schedulingId: Id }
  | { type: 'task/add'; input: TaskInput }
  | { type: 'task/edit'; taskId: Id; patch: Partial<TaskInput> }
  | { type: 'task/status'; taskId: Id; status: TaskStatus; reason: string | null }
  | { type: 'task/dismiss'; taskId: Id }
  | { type: 'suggestion/edit'; suggestionId: Id; patch: SuggestionPatch }
  | { type: 'suggestion/dismiss'; suggestionId: Id }
  | { type: 'suggestion/confirm'; suggestionIds: Id[]; by: Id }
  | { type: 'proposal/respond'; meetingId: Id; userId: Id; accept: boolean; feedback: string | null }
  | { type: 'feedback/undo'; meetingId: Id; userId: Id }
  | { type: 'notice/read'; userId: Id; noticeIds: Id[] }
  | { type: 'meeting/transcript'; meetingId: Id; text: string }

const now = (s: DemoState): IsoDateTime => s.clockNow

/** 누적 양보 단계를 한 칸 올린다. 가장 높은 단계면 그대로 */
export const nextYieldLevel = (level: YieldLevel): YieldLevel =>
  YIELD_LEVELS[Math.min(YIELD_LEVELS.indexOf(level) + 1, YIELD_LEVELS.length - 1)]

/**
 * 남긴 한 줄에서 다음 조율에 쓸 선호 한 가지를 고른다(실서버에서는 에이전트가 한다. 시연용 간단 해석).
 * 시간과 상관없는 말이면 아무것도 바꾸지 않는다(브리프 "억지로 무언가 바꾸지 않습니다").
 */
export function feedbackChange(text: string): string | null {
  const day = text.match(/([월화수목금토일])요일/)
  if (day) return `다음부터 ${day[1]}요일은 덜 잡을게요`
  if (/이르|일찍|아침|오전/.test(text)) return '다음부터 오전 이른 시간은 덜 잡을게요'
  if (/늦|밤/.test(text)) return '다음부터 밤 늦은 시간은 덜 잡을게요'
  if (/수업|빠듯|이동|바로 뒤/.test(text)) return '다음부터 수업 바로 뒤는 30분 띄워서 잡을게요'
  return null
}

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

    case 'room/create': {
      // 시연 데이터(팀원·할 일)는 그대로 두고 방 정보만 바꾼다
      const { name, description, startDate, dueDate, memberCount } = action.input
      return { ...s, room: { ...s.room, name, description, startDate, dueDate, memberCount } }
    }

    case 'scheduling/start': {
      // 아직 확정 전인 지난 조율 결과는 새 조율로 바뀐다. 확정된 회의는 그대로 둔다
      const replaced = new Set(
        s.meetings
          .filter((m) => m.status === 'proposed' && s.schedulings.some((c) => c.meetingId === m.id))
          .map((m) => m.id),
      )
      const { input } = action
      return {
        ...s,
        meetings: s.meetings.filter((m) => !replaced.has(m.id)),
        proposals: s.proposals.filter((p) => !replaced.has(p.meetingId)),
        schedulings: [
          ...s.schedulings.filter((c) => c.meetingId !== null && !replaced.has(c.meetingId)),
          {
            id: `c${s.nextSeq}`,
            topic: input.topic,
            windowStart: `${input.windowStart}T00:00:00+09:00`,
            windowEnd: `${input.windowEnd}T23:59:00+09:00`,
            durationMin: input.durationMin,
            mode: input.mode,
            status: 'running',
            script: DEMO_SCENARIO.script,
            meetingId: null,
          },
        ],
        nextSeq: s.nextSeq + 1,
      }
    }

    case 'scheduling/finish': {
      // 마지막 판단 에이전트가 낸 시간이 회의안이 된다
      const c = s.schedulings.find((x) => x.id === action.schedulingId)
      const lastJudge = c?.script.findLast((u) => u.kind === 'judge')
      if (!c || c.status !== 'running' || lastJudge?.kind !== 'judge') return s
      const meetingId = `m${s.nextSeq}`
      const { result } = DEMO_SCENARIO
      const getter = s.members.find((m) => m.id === result.gets)
      return {
        ...s,
        schedulings: s.schedulings.map((x) => (x.id === c.id ? { ...x, status: 'agreed', meetingId } : x)),
        meetings: [
          ...s.meetings,
          { id: meetingId, topic: c.topic, ...lastJudge.slot, status: 'proposed', transcript: [], minutes: null },
        ],
        proposals: [
          ...s.proposals,
          {
            ...result,
            meetingId,
            settled: false,
            getsFrom: getter?.yieldLevel ?? result.getsFrom,
            responses: Object.fromEntries(result.burdens.map((b) => [b.userId, '대기' as const])),
            feedback: {},
          },
        ],
        agentLog: [
          { id: `a${s.nextSeq}`, at: now(s), what: '조율 결과를 냈어요', why: result.rationale },
          ...s.agentLog,
        ],
        nextSeq: s.nextSeq + 1,
      }
    }

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
      const p = s.proposals.find((x) => x.meetingId === action.meetingId)
      const m = s.meetings.find((x) => x.id === action.meetingId)
      if (!p || !m) return s
      const feedback: Record<Id, SeedFeedback> = action.feedback
        ? { ...p.feedback, [action.userId]: { text: action.feedback, change: feedbackChange(action.feedback), undone: false } }
        : p.feedback
      // 조정안은 이미 확정이라 피드백 한 줄만 받는다
      const responses = p.settled ? p.responses : { ...p.responses, [action.userId]: action.accept ? '수락' : '거절' } as const
      const proposals = s.proposals.map((x) => (x === p ? { ...x, feedback, responses } : x))

      // 응답할 사람이 모두 수락하면 회의가 자동으로 확정되고, 맞춰 준 사람의 양보 단계가 오른다
      const allAccepted = Object.values(responses).every((r) => r === '수락')
      if (p.settled || m.status !== 'proposed' || !allAccepted) return { ...s, proposals }
      return {
        ...s,
        proposals,
        meetings: s.meetings.map((x) => (x.id === m.id ? { ...x, status: 'confirmed' } : x)),
        members: s.members.map((x) => (x.id === p.gets ? { ...x, yieldLevel: nextYieldLevel(p.getsFrom) } : x)),
        yieldRecords: p.gets
          ? [{ id: `y${s.nextSeq}`, meetingLabel: `${formatMonthDay(m.startAt)} 회의`, userId: p.gets, why: p.yieldWhy }, ...s.yieldRecords]
          : s.yieldRecords,
        nextSeq: s.nextSeq + 1,
      }
    }

    case 'feedback/undo':
      return {
        ...s,
        proposals: s.proposals.map((p) => {
          const mine = p.feedback[action.userId]
          if (p.meetingId !== action.meetingId || !mine) return p
          return { ...p, feedback: { ...p.feedback, [action.userId]: { ...mine, undone: true } } }
        }),
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
