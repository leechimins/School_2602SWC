import dayjs, { type Dayjs } from 'dayjs'
import type { Id, IsoDateTime } from '../types/common.ts'
import { daysUntil, formatMonthDay, formatTimeRange, weekday } from '../lib/date.ts'
import type { NoticeKind } from '../types/notification.ts'
import type { Preferences, ScheduleItemInput, ScheduleItemPatch } from '../types/me.ts'
import type { RecordInput, SuggestionPatch } from '../types/meeting.ts'
import { YIELD_LEVELS, type RoomInput, type YieldLevel } from '../types/room.ts'
import type { SchedulingInput } from '../types/scheduling.ts'
import type { TaskInput, TaskStatus } from '../types/task.ts'
import {
  DEMO_EVERYTIME_CLASSES,
  DEMO_GOOGLE_EVENTS,
  DEMO_RECORDING,
  DEMO_SCENARIO,
  OFFSTAGE,
  SEED,
  USER,
  rerunScenario,
  type DemoState,
  type SeedFeedback,
  type SeedMeeting,
  type SeedNotice,
  type SeedScheduleItem,
  type SeedScheduling,
  type SeedTask,
} from './seed.ts'

// 액션 표: 목 데이터를 바꾸는 동작을 모두 여기 모은다.
// 화면은 api/ 함수를 부르고, 목 모드의 api 함수가 dispatch(액션)을 보낸다.
// 실서버로 바꾸면 같은 동작을 서버가 하므로, 이 표는 서버 API 목록과 1:1로 맞춘다.
export type Action =
  | { type: 'clock/move'; minutes: number }
  | { type: 'clock/reset' }
  | { type: 'room/create'; input: RoomInput }
  | { type: 'scheduling/start'; input: SchedulingInput }
  | { type: 'scheduling/finish'; schedulingId: Id }
  | { type: 'task/add'; input: TaskInput; meetingId: Id | null; by: Id }
  | { type: 'task/edit'; taskId: Id; patch: Partial<TaskInput> }
  | { type: 'task/status'; taskId: Id; status: TaskStatus; reason: string | null; by: Id }
  | { type: 'task/dismiss'; taskId: Id }
  | { type: 'task/keep'; taskId: Id }
  | { type: 'suggestion/edit'; suggestionId: Id; patch: SuggestionPatch }
  | { type: 'suggestion/dismiss'; suggestionId: Id }
  | { type: 'suggestion/confirm'; suggestionIds: Id[]; by: Id }
  | { type: 'proposal/respond'; meetingId: Id; userId: Id; accept: boolean; feedback: string | null }
  | { type: 'feedback/undo'; meetingId: Id; userId: Id }
  | { type: 'notice/read'; userId: Id; noticeIds: Id[] }
  | { type: 'notice/late' }
  | { type: 'meeting/create'; meetingId: Id; input: RecordInput }
  | { type: 'meeting/transcript'; meetingId: Id; text: string }
  | { type: 'meeting/summarize'; meetingId: Id }
  | { type: 'me/prefs'; userId: Id; prefs: Preferences }
  | { type: 'me/schedule-add'; userId: Id; input: ScheduleItemInput }
  | { type: 'me/schedule-edit'; itemId: Id; patch: ScheduleItemPatch }
  | { type: 'me/schedule-delete'; itemId: Id }
  | { type: 'me/everytime'; userId: Id }
  | { type: 'me/google'; userId: Id }

const now = (s: DemoState): IsoDateTime => s.clockNow

/** 조율 하나에 쓸 수 있는 라운드. 사람이 거절해 다시 돌아도 새로 주지 않는다(백엔드 MAX_ROUNDS) */
export const MAX_ROUNDS = 3
export const roundsUsed = (c: SeedScheduling) => Math.max(...c.script.map((u) => u.round))

/** 누적 양보 점수 → 단계. 1점부터 조금, 3점부터 많이 (room/service.py yield_level) */
export const yieldLevelOf = (total: number): YieldLevel =>
  total >= 3 ? '많이 맞춰 줌' : total >= 1 ? '조금 맞춰 줌' : '아직 없음'

/** 이 불편을 감수하면 받는 양보 점수: 괜찮음(1점) 0, 조금(2~3점) +1, 많이(4~5점) +2 (scorer.yield_points) */
export const yieldPointsOf = (score: number) => (score >= 4 ? 2 : score >= 2 ? 1 : 0)

/** 늦음은 상태가 아니라 뱃지다: 기한이 오늘보다 앞이고 안 끝났으면 (minutes/tasks.py is_late) */
export const isLate = (t: SeedTask, now: Dayjs) => t.status !== '완료' && t.dueDate !== null && daysUntil(t.dueDate, now) < 0

/** 기록에 쓰는 회의 시각: 11월 18일(수) 16:00–18:00 (meeting/prompts.py when) */
const when = (startAt: IsoDateTime, endAt: IsoDateTime) => `${formatMonthDay(startAt)}(${weekday(startAt)}) ${formatTimeRange(startAt, endAt)}`

const nameOf = (s: DemoState, id: Id) => s.members.find((m) => m.id === id)?.name ?? '팀원'

/**
 * 알림을 사람마다 한 장씩 쌓는다 (shared/notify.py emit). 같은 사람에게 같은 키(종류+dedupe)는 한 번만.
 * 알림은 그때그때 계산하지 않고 남는다 — 막힘을 풀어도 막힘 알림은 그대로다(서버와 같다).
 */
function emit(
  s: DemoState,
  userIds: Id[],
  n: { kind: NoticeKind; reason: string; dedupe: string; taskId?: Id; meetingId?: Id },
): DemoState {
  const key = `${n.kind}:${n.dedupe}`
  const fresh = [...new Set(userIds)].filter((u) => !s.notices.some((x) => x.userId === u && x.dedupe === key))
  const added: SeedNotice[] = fresh.map((userId, i) => ({
    id: `n${s.nextSeq + i}`, seq: s.nextSeq + i, userId, kind: n.kind, reason: n.reason,
    taskId: n.taskId ?? null, meetingId: n.meetingId ?? null, dedupe: key, createdAt: now(s), read: false,
  }))
  return added.length ? { ...s, notices: [...s.notices, ...added], nextSeq: s.nextSeq + added.length } : s
}

/** 에이전트가 한 일 한 줄 (notice/agent_log.py record) */
const record = (s: DemoState, what: string, why: string): DemoState => ({
  ...s,
  agentLog: [{ id: `a${s.nextSeq}`, at: now(s), what, why }, ...s.agentLog],
  nextSeq: s.nextSeq + 1,
})

/**
 * 늦은 할 일마다 늦음 알림 (minutes/tasks.py emit_late). 서버는 할 일 목록을 부를 때 돈다.
 * 받는 사람은 담당자, 담당자가 없으면 전원. 같은 할 일·같은 기한이면 한 번만. 새로 생긴 게 없으면 같은 객체를 돌려준다.
 */
export function emitLate(s: DemoState): DemoState {
  const today = dayjs(now(s))
  return s.tasks
    .filter((t) => !t.dismissed && isLate(t, today))
    .reduce(
      (acc, t) =>
        emit(acc, t.assigneeId ? [t.assigneeId] : acc.members.map((m) => m.id), {
          kind: '늦음',
          reason: `'${t.title}' 기한(${dayjs(t.dueDate).format('M/D')})이 지났습니다.`,
          dedupe: `task${t.id}:due${t.dueDate}`,
          taskId: t.id,
        }),
      s,
    )
}

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

/** 직접 쓰기 한 줄: "민지: 발표 대본은 제가 쓸게요"처럼 앞에 이름이 있으면 말한 사람으로 읽는다 */
function parseLine(s: DemoState, line: string) {
  const m = line.match(/^([^:：]{1,10})[:：]\s*(.+)$/)
  const speaker = m && s.members.find((x) => x.name === m[1].trim())
  return speaker ? { speakerId: speaker.id, text: m[2] } : { speakerId: null, text: line }
}

/**
 * 회의록 정리(실서버에서는 AI). 시연 받아적기 대본이면 준비한 요약·제안을 내고,
 * 아니면 앞의 말 몇 줄을 논의로만 남긴다 — 할 일을 지어내지 않고 "뽑을 할 일을 못 찾음"으로 둔다.
 */
function summarize(m: SeedMeeting) {
  const isDemo = m.transcript.some((l) => l.text === DEMO_RECORDING.lines[0].text)
  const minutes = isDemo
    ? { headline: m.topic, status: 'done' as const, ...DEMO_RECORDING.minutes }
    : { headline: m.topic, status: 'done' as const, decisions: [], discussions: m.transcript.slice(0, 3).map((l) => l.text), pendings: [] }
  return { minutes, suggestions: isDemo ? DEMO_RECORDING.suggestions : [] }
}

const updateTask = (s: DemoState, id: Id, fn: (t: SeedTask) => SeedTask): DemoState => ({
  ...s,
  tasks: s.tasks.map((t) => (t.id === id ? fn(t) : t)),
})

/** 한 곳(에브리타임·구글)에서 온 일정을 통째로 바꾼다. 연결돼 있는지는 그곳에서 온 일정이 있는지로 본다 */
function replaceSource(
  s: DemoState,
  userId: Id,
  source: SeedScheduleItem['source'],
  rows: Omit<SeedScheduleItem, 'id' | 'userId' | 'groupId'>[],
): DemoState {
  const kept = s.scheduleItems.filter((i) => !(i.userId === userId && i.source === source))
  const added = rows.map((r, i) => ({ ...r, id: `s${s.nextSeq + i}`, userId, groupId: s.nextSeq + i }))
  return {
    ...s,
    scheduleItems: [...kept, ...added],
    nextSeq: s.nextSeq + added.length,
  }
}

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

    case 'me/prefs':
      return { ...s, prefs: { ...s.prefs, [action.userId]: action.prefs } }

    case 'me/schedule-add': {
      // 요일마다 한 줄, 같은 묶음 번호
      const { userId, input } = action
      const rows = input.days.map((d, i) => ({
        id: `s${s.nextSeq + i}`, userId, groupId: s.nextSeq, title: input.title, kind: input.kind,
        source: 'manual' as const, weekday: d.weekday, startMin: d.startHour * 60, endMin: d.endHour * 60,
      }))
      return { ...s, scheduleItems: [...s.scheduleItems, ...rows], nextSeq: s.nextSeq + rows.length }
    }

    case 'me/schedule-edit': {
      const { title, startHour, endHour } = action.patch
      const edit = (i: SeedScheduleItem) => (i.id === action.itemId ? { ...i, title, startMin: startHour * 60, endMin: endHour * 60 } : i)
      return { ...s, scheduleItems: s.scheduleItems.map(edit) }
    }

    case 'me/schedule-delete':
      return { ...s, scheduleItems: s.scheduleItems.filter((i) => i.id !== action.itemId) }

    case 'me/everytime':
      // 다시 불러오기: 이전 에브리타임 수업을 지우고 새로 넣는다(직접 넣은 일정은 그대로)
      return replaceSource(s, action.userId, 'everytime', DEMO_EVERYTIME_CLASSES)

    case 'me/google':
      return replaceSource(s, action.userId, 'google', DEMO_GOOGLE_EVENTS)

    case 'scheduling/start': {
      // 도는 조율이나 수락을 기다리는 회의가 있으면 api/scheduling.ts가 서버처럼 409로 먼저 막는다
      const { input } = action
      return {
        ...s,
        schedulings: [
          ...s.schedulings,
          {
            id: `c${s.nextSeq}`,
            topic: input.topic,
            windowStart: `${input.windowStart}T00:00:00+09:00`,
            windowEnd: `${input.windowEnd}T23:59:00+09:00`,
            durationMin: input.durationMin,
            mode: input.mode,
            status: 'running',
            script: DEMO_SCENARIO.script,
            result: DEMO_SCENARIO.result,
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
      const { result } = c
      const getter = s.members.find((m) => m.id === result.gets)
      const proposed: DemoState = {
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
            schedulingId: c.id,
            settled: false,
            getsFrom: getter ? yieldLevelOf(getter.yieldTotal) : result.getsFrom,
            // 화면에 없는 팀원은 바로 수락해 둔다. 지수·민지가 답하면 그 자리에서 확정되는 장면이 나온다
            responses: Object.fromEntries(
              result.burdens.map((b) => [b.userId, OFFSTAGE.includes(b.userId) ? ('수락' as const) : ('대기' as const)]),
            ),
            feedback: {},
          },
        ],
        nextSeq: s.nextSeq + 1,
      }
      // 회의에 들 사람 모두에게 회의 제안 알림, 방 전체에 기록 한 줄 (meeting/agent_loop.py)
      const told = emit(proposed, result.burdens.map((b) => b.userId), {
        kind: '회의 제안',
        reason: `${c.topic} 일정이 나왔어요. 수락/거절해 주세요.`,
        dedupe: `meeting${meetingId}`,
        meetingId,
      })
      return record(told, `${c.topic} 제안 · ${when(lastJudge.slot.startAt, lastJudge.slot.endAt)}`, result.rationale || '팀 전체로 가장 덜 불편한 시간이에요')
    }

    case 'task/add': {
      const id = `t${s.nextSeq}`
      const added: SeedTask = {
        id,
        ...action.input,
        status: '시작 전',
        blockedReason: null,
        meetingId: action.meetingId, // 회의록에서 추가하면 그 회의, 할 일 탭에서는 null = "직접 추가"
        confirmedBy: action.by,
        confirmedAt: now(s),
        doneMeetingId: null,
        dismissed: false,
        unneeded: null,
      }
      return { ...s, tasks: [...s.tasks, added], nextSeq: s.nextSeq + 1 }
    }

    case 'task/edit':
      return updateTask(s, action.taskId, (t) => ({ ...t, ...action.patch }))

    case 'task/status': {
      // 같은 상태를 보내면 아무 일도 없다 (minutes/task_router.py change_status)
      const before = s.tasks.find((t) => t.id === action.taskId)
      if (!before || before.status === action.status) return s
      const changed = updateTask(s, action.taskId, (t) => ({
        ...t,
        status: action.status,
        blockedReason: action.status === '막힘' ? action.reason : null, // 막힌 이유는 서버에 아직 없다(백엔드 요청). 목에서만 남긴다
        doneMeetingId: action.status === '완료' ? t.doneMeetingId : null, // 되돌리면 "회의에서 끝난 일"에서도 빠진다
      }))
      // 막힘·완료로 바뀌면 바꾼 사람을 뺀 팀원에게 알린다 (minutes/tasks.py emit_status). 바뀔 때마다 새 알림이다
      if (action.status !== '막힘' && action.status !== '완료') return changed
      const who = nameOf(s, action.by)
      return emit(changed, s.members.map((m) => m.id).filter((id) => id !== action.by), {
        kind: action.status,
        reason: action.status === '막힘'
          ? `${who}님이 '${before.title}'에서 막혔다고 표시했습니다.`
          : `${who}님이 '${before.title}' 할 일을 완료했습니다.`,
        dedupe: `task${before.id}:change${s.nextSeq}`,
        taskId: before.id,
      })
    }

    case 'task/dismiss':
      return updateTask(s, action.taskId, (t) => ({ ...t, dismissed: true }))

    case 'task/keep':
      return updateTask(s, action.taskId, (t) => ({ ...t, unneeded: t.unneeded && { ...t.unneeded, kept: true } }))

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
        confirmedAt: now(s),
        doneMeetingId: null,
        dismissed: false,
        unneeded: null,
      }))
      return {
        ...s,
        tasks: [...s.tasks, ...confirmed],
        suggestions: s.suggestions.filter((g) => !action.suggestionIds.includes(g.id)),
        nextSeq: s.nextSeq + picked.length,
      }
    }

    case 'proposal/respond': {
      // 규칙은 meeting/router.py respond. 응답할 사람이 아니거나 끝난 회의면 api/scheduling.ts가 먼저 막는다
      const p = s.proposals.find((x) => x.meetingId === action.meetingId)
      const m = s.meetings.find((x) => x.id === action.meetingId)
      if (!p || !m || p.responses[action.userId] === undefined) return s
      const feedback: Record<Id, SeedFeedback> = action.feedback
        ? { ...p.feedback, [action.userId]: { text: action.feedback, change: feedbackChange(action.feedback), undone: false } }
        : p.feedback
      // 이미 확정된 회의(조정안 포함)는 피드백 한 줄만 받는다
      if (m.status === 'confirmed') {
        return { ...s, proposals: s.proposals.map((x) => (x === p ? { ...x, feedback } : x)) }
      }
      if (m.status !== 'proposed') return s
      const responses = { ...p.responses, [action.userId]: action.accept ? '수락' : '거절' } as const

      // 거절했는데 라운드가 남았으면 바로 다시 조율한다(백엔드 rerun): 옛 회의는 취소, 같은 조율에 다음 라운드를 잇는다
      const c = s.schedulings.find((x) => x.id === p.schedulingId)
      if (!action.accept && c && roundsUsed(c) < MAX_ROUNDS) {
        const jisu = s.members.find((x) => x.id === USER.jisu)
        const jisuLevel = yieldLevelOf(jisu?.yieldTotal ?? 0) // 다시 잡은 시간에 맞춰 주는 사람
        const next = rerunScenario(roundsUsed(c) + 1, nameOf(s, action.userId), action.feedback, {
          from: jisuLevel,
          to: nextYieldLevel(jisuLevel),
        })
        const reopened: DemoState = {
          ...s,
          proposals: s.proposals.map((x) => (x === p ? { ...x, feedback, responses } : x)),
          meetings: s.meetings.map((x) => (x.id === m.id ? { ...x, status: 'cancelled' } : x)),
          schedulings: s.schedulings.map((x) =>
            x.id === c.id ? { ...x, status: 'running', meetingId: null, script: [...x.script, ...next.script], result: next.result } : x,
          ),
        }
        return record(reopened, `${m.topic} 다시 조율`, `${nameOf(s, action.userId)} 님이 그 시간은 어렵다고 했어요`)
      }

      // 라운드를 다 쓴 뒤의 거절은 다시 돌지 않고 그 사람을 불참으로 둔다.
      // 거절하지 않은 사람이 모두 수락하면 회의가 자동으로 확정된다
      const absent = action.accept ? p.absent : action.userId
      const proposals = s.proposals.map((x) => (x === p ? { ...x, feedback, responses, absent } : x))
      const attending = Object.keys(responses).filter((id) => responses[id] !== '거절')
      if (attending.length === 0 || !attending.every((id) => responses[id] === '수락')) return { ...s, proposals }

      // 양보 점수는 와 주는 사람만 자기 불편만큼 받는다 (agent_loop.award_yield)
      const gained = p.burdens
        .filter((b) => attending.includes(b.userId) && yieldPointsOf(b.score) > 0)
        .map((b, i) => ({ ...b, points: yieldPointsOf(b.score), recordId: `y${s.nextSeq + i}` }))
      const confirmed: DemoState = {
        ...s,
        proposals,
        meetings: s.meetings.map((x) => (x.id === m.id ? { ...x, status: 'confirmed' } : x)),
        members: s.members.map((x) => {
          const got = gained.find((g) => g.userId === x.id)
          return got ? { ...x, yieldTotal: x.yieldTotal + got.points } : x
        }),
        yieldRecords: [
          ...gained.map((g) => ({
            id: g.recordId,
            meetingLabel: `${formatMonthDay(m.startAt)} 회의`,
            userId: g.userId,
            why: g.score >= 4 ? '많이 불편한 시간을 맞춰 줬어요' : '조금 불편한 시간을 맞춰 줬어요', // 숫자 없이 (notice/router.py _양보말)
          })).reverse(),
          ...s.yieldRecords,
        ],
        nextSeq: s.nextSeq + gained.length,
      }
      const left = Object.keys(responses).filter((id) => responses[id] === '거절').map((id) => nameOf(s, id))
      const told = emit(confirmed, Object.keys(responses), {
        kind: '회의 확정',
        reason: `${m.topic} 일정이 확정됐어요.${left.length ? ` ${left.join(', ')} 님은 빠져요.` : ''}`,
        dedupe: `meeting${m.id}`,
        meetingId: m.id,
      })
      return record(told, `${m.topic} 확정`, left.length ? `${left.join(', ')} 님은 빠지고 나머지가 모두 수락했어요` : '모두 수락했어요')
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
      // 남의 알림은 ids에 넣어도 안 바뀐다 (notice/router.py mark_read)
      const ids = new Set(action.noticeIds)
      return { ...s, notices: s.notices.map((n) => (n.userId === action.userId && ids.has(n.id) ? { ...n, read: true } : n)) }
    }

    case 'notice/late':
      return emitLate(s)

    case 'meeting/create': {
      // 잡힌 회의 없이 바로 기록: 지금 시작한 한 시간짜리 확정 회의로 둔다. 끝 시각이 지나면 지난 회의로 넘어간다
      const start = dayjs(now(s))
      const meeting: SeedMeeting = {
        id: action.meetingId,
        topic: action.input.topic?.trim() || '회의',
        startAt: start.format(),
        endAt: start.add(1, 'hour').format(),
        mode: action.input.mode,
        status: 'confirmed',
        transcript: [],
        minutes: null,
      }
      return { ...s, meetings: [...s.meetings, meeting], nextSeq: s.nextSeq + 1 }
    }

    case 'meeting/transcript': {
      const lines = action.text
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => parseLine(s, line))
      return {
        ...s,
        meetings: s.meetings.map((m) => (m.id === action.meetingId ? { ...m, transcript: lines } : m)),
      }
    }

    case 'meeting/summarize': {
      const m = s.meetings.find((x) => x.id === action.meetingId)
      if (!m || m.transcript.length === 0) return s
      const { minutes, suggestions } = summarize(m)
      // 서버는 정리해도 회의 상태를 바꾸지 않고, 에이전트가 한 일에도 남기지 않는다 (minutes/record_router.py summarize_meeting)
      return {
        ...s,
        meetings: s.meetings.map((x) => (x.id === m.id ? { ...x, minutes } : x)),
        suggestions: [
          ...s.suggestions.filter((g) => g.meetingId !== m.id), // 다시 정리하면 확정 전 제안은 새로 뽑은 것으로 바뀐다
          ...suggestions.map((g, i) => ({ ...g, id: `s${s.nextSeq + i}`, meetingId: m.id })),
        ],
        nextSeq: s.nextSeq + suggestions.length,
      }
    }
  }
}
