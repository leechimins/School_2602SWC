import dayjs, { type Dayjs } from 'dayjs'
import { daysUntil, formatMD, formatSlot, formatTime, toIsoDate } from '../lib/date.ts'
import { withJosa } from '../lib/korean.ts'
import type { Id } from '../types/common.ts'
import type { Home } from '../types/home.ts'
import type { CoordinatingBrief, MeetingBrief, MeetingDetail, MeetingSummary, Schedule } from '../types/meeting.ts'
import { NOTICE_KINDS, type ActivityLog, type Notice, type NoticeList } from '../types/notification.ts'
import type { Room } from '../types/room.ts'
import type { Burden, Proposal, Scheduling, Utterance } from '../types/scheduling.ts'
import type { Task, TeamTasks } from '../types/task.ts'
import type { DemoState, SeedMeeting, SeedTask } from './seed.ts'

// 목 데이터(원본) → 화면이 받는 모양. 서버가 할 일을 대신한다:
// 보는 사람(viewer)마다 다른 값(내 점수, can_*), 시연 시계(now) 기준 판정(늦음, 알림)을 여기서 만든다.
// 남의 불편 점수는 숫자로 내보내지 않는다(브리프 "내부 숫자는 보이지 않습니다").

const NOT_FOUND = (what: string) => new Error(`${withJosa(what, '을/를')} 찾을 수 없어요`)

/** 불편 점수 → 남에게 보이는 단계: 1점 괜찮음, 2~3점 조금, 4~5점 많이 */
export function burdenOf(score: number): Burden {
  if (score <= 1) return '괜찮음'
  return score <= 3 ? '조금' : '많이'
}

/** 이번에 받을 양보 점수: 조금 불편 +1, 많이 불편 +2 */
const yieldPointsOf = (score: number) => (score >= 4 ? 2 : score >= 2 ? 1 : 0)

const nameOf = (s: DemoState, id: Id | null) => s.members.find((m) => m.id === id)?.name ?? null
const liveTasks = (s: DemoState) => s.tasks.filter((t) => !t.dismissed)
const isLate = (t: SeedTask, now: Dayjs) => t.status !== '완료' && t.dueDate !== null && daysUntil(t.dueDate, now) < 0

export function toTask(s: DemoState, t: SeedTask, viewer: Id, now: Dayjs): Task {
  const meeting = s.meetings.find((m) => m.id === t.meetingId)
  return {
    id: t.id,
    title: t.title,
    dueDate: t.dueDate,
    assigneeId: t.assigneeId,
    assigneeName: nameOf(s, t.assigneeId),
    status: t.status,
    blockedReason: t.blockedReason,
    source: meeting ? { meetingId: meeting.id, heldOn: toIsoDate(meeting.startAt), topic: meeting.topic } : null,
    confirmedByName: nameOf(s, t.confirmedBy),
    confirmedAt: null,
    isLate: isLate(t, now),
    canChangeStatus: t.assigneeId === viewer,
    canEdit: true,
  }
}

const byDue = (a: Task, b: Task) => (a.dueDate ?? '9999').localeCompare(b.dueDate ?? '9999')

export function buildRoom(s: DemoState, viewer: Id): Room {
  const { room } = s
  const members = [...s.members].sort((a, b) => Number(b.id === room.leaderId) - Number(a.id === room.leaderId))
  return {
    ...room,
    joinedCount: s.members.length,
    members: members.map((m) => ({
      id: m.id,
      name: m.name,
      isLeader: m.id === room.leaderId,
      isMe: m.id === viewer,
      yieldLevel: m.yieldLevel,
    })),
    canStartScheduling: viewer === room.leaderId,
  }
}

export function buildTeamTasks(s: DemoState, viewer: Id, now: Dayjs): TeamTasks {
  const tasks = liveTasks(s).map((t) => toTask(s, t, viewer, now)).sort(byDue)
  return {
    tasks,
    counts: s.members.map((m) => ({
      userId: m.id,
      name: m.name,
      remaining: tasks.filter((t) => t.assigneeId === m.id && t.status !== '완료').length,
    })),
    suggestionCount: s.suggestions.length,
  }
}

export function buildMyTasks(s: DemoState, viewer: Id, now: Dayjs): Task[] {
  return liveTasks(s)
    .filter((t) => t.assigneeId === viewer)
    .map((t) => toTask(s, t, viewer, now))
    .sort(byDue)
}

function toMeetingBrief(s: DemoState, m: SeedMeeting, viewer: Id): MeetingBrief {
  const proposal = s.proposals.find((p) => p.meetingId === m.id)
  return {
    id: m.id,
    topic: m.topic,
    startAt: m.startAt,
    endAt: m.endAt,
    mode: m.mode,
    status: m.status,
    settled: proposal?.settled ?? false,
    myState: proposal?.responses[viewer] ?? null,
    pendingCount: proposal ? Object.values(proposal.responses).filter((r) => r === '대기').length : 0,
    suggestionCount: s.suggestions.filter((g) => g.meetingId === m.id).length,
  }
}

const isUpcoming = (m: SeedMeeting, now: Dayjs) =>
  (m.status === 'proposed' || m.status === 'confirmed') && dayjs(m.endAt).isAfter(now)

export function buildSchedule(s: DemoState, viewer: Id, now: Dayjs): Schedule {
  const coordinating: CoordinatingBrief[] = s.schedulings
    .filter((c) => c.status === 'running')
    .map(({ id, topic, windowStart, windowEnd, status }) => ({ id, topic, windowStart, windowEnd, status }))
  const upcoming = s.meetings.filter((m) => isUpcoming(m, now)).sort((a, b) => a.startAt.localeCompare(b.startAt))
  const past = s.meetings
    .filter((m) => m.status !== 'cancelled' && !isUpcoming(m, now))
    .sort((a, b) => b.startAt.localeCompare(a.startAt))
  return {
    coordinating,
    upcoming: upcoming.map((m) => toMeetingBrief(s, m, viewer)),
    past: past.map((m) => toMeetingBrief(s, m, viewer)),
  }
}

export function buildHome(s: DemoState, viewer: Id, now: Dayjs): Home {
  const schedule = buildSchedule(s, viewer, now)
  return {
    roomName: s.room.name,
    today: toIsoDate(now),
    startDate: s.room.startDate,
    dueDate: s.room.dueDate,
    dDay: daysUntil(s.room.dueDate, now),
    nextMeeting: schedule.upcoming[0] ?? null,
    coordinating: schedule.coordinating[0] ?? null,
    myTasks: buildMyTasks(s, viewer, now),
    unreadCount: buildNotices(s, viewer, now).unreadCount,
    canStartScheduling: viewer === s.room.leaderId,
    inviteCode: s.room.inviteCode,
    joinedCount: s.members.length,
    memberCount: s.room.memberCount,
  }
}

export function buildScheduling(s: DemoState, schedulingId: Id, viewer: Id): Scheduling {
  const c = s.schedulings.find((x) => x.id === schedulingId)
  if (!c) throw NOT_FOUND('조율')
  const utterances = c.script.map((u, seq): Utterance => {
    const base = { seq, round: u.round, text: u.text, answer: null, burden: null, myScore: null, slot: null, yieldChanges: [] }
    if (u.kind === 'judge') {
      return {
        ...base,
        kind: 'judge',
        speakerId: null,
        speakerName: null,
        slot: u.slot,
        yieldChanges: u.yieldChanges.map((y) => ({ userId: y.who, name: nameOf(s, y.who) ?? '', from: y.from, to: y.to })),
      }
    }
    const who = { speakerId: u.who, speakerName: nameOf(s, u.who) }
    if (u.kind === 'appeal') return { ...base, ...who, kind: 'appeal' }
    const mine = u.who === viewer
    return { ...base, ...who, kind: 'answer', answer: u.answer, burden: burdenOf(u.score), myScore: mine ? u.score : null }
  })
  return {
    id: c.id,
    topic: c.topic,
    windowStart: c.windowStart,
    windowEnd: c.windowEnd,
    durationMin: c.durationMin,
    mode: c.mode,
    status: c.status,
    roundsUsed: Math.max(...c.script.map((u) => u.round)),
    utterances,
    proposalId: c.meetingId,
  }
}

export function buildProposal(s: DemoState, meetingId: Id, viewer: Id): Proposal {
  const m = s.meetings.find((x) => x.id === meetingId)
  const p = s.proposals.find((x) => x.meetingId === meetingId)
  if (!m || !p) throw NOT_FOUND('회의')
  const mine = p.burdens.find((b) => b.userId === viewer) // 불참안에서 빠진 사람이면 없다
  const myState = p.responses[viewer] ?? null
  return {
    id: m.id,
    topic: m.topic,
    startAt: m.startAt,
    endAt: m.endAt,
    mode: m.mode,
    confirmed: m.status === 'confirmed' || p.settled,
    settled: p.settled,
    rationale: p.rationale,
    myScore: mine?.score ?? null,
    myReason: mine?.reason ?? '',
    myYieldPoints: mine && p.gets === viewer ? yieldPointsOf(mine.score) : 0,
    myState,
    canRespond: myState !== null && m.status === 'proposed',
    feedbackOnly: p.settled,
    absentName: nameOf(s, p.absent),
    responders: p.burdens.map((b) => ({
      userId: b.userId,
      name: nameOf(s, b.userId) ?? '',
      state: p.responses[b.userId] ?? '대기',
      burden: burdenOf(b.score),
      reason: b.reason,
      yieldLevel: s.members.find((x) => x.id === b.userId)?.yieldLevel ?? '아직 없음',
      feedback: p.feedback[b.userId] ?? null,
    })),
  }
}

export function buildMeetingDetail(s: DemoState, meetingId: Id, viewer: Id, now: Dayjs): MeetingDetail {
  const m = s.meetings.find((x) => x.id === meetingId)
  if (!m) throw NOT_FOUND('회의')
  const p = s.proposals.find((x) => x.meetingId === m.id)
  const attendeeIds = p ? Object.keys(p.responses).filter((id) => p.responses[id] === '수락') : s.members.map((x) => x.id)
  return {
    id: m.id,
    topic: m.topic,
    startAt: m.startAt,
    endAt: m.endAt,
    mode: m.mode,
    status: m.status,
    attendees: attendeeIds.map((id) => nameOf(s, id) ?? ''),
    transcript: m.transcript.map((line, seq) => ({ seq, speakerId: line.speakerId, speakerName: nameOf(s, line.speakerId), text: line.text })),
    minutes: m.minutes,
    tasks: liveTasks(s).filter((t) => t.meetingId === m.id).map((t) => toTask(s, t, viewer, now)),
    suggestions: s.suggestions
      .filter((g) => g.meetingId === m.id)
      .map((g) => ({ id: g.id, title: g.title, dueDate: g.dueDate, assigneeId: g.assigneeId, assigneeName: nameOf(s, g.assigneeId) })),
  }
}

export function buildMeetingList(s: DemoState): MeetingSummary[] {
  return s.meetings
    .filter((m) => m.status === 'done')
    .sort((a, b) => b.startAt.localeCompare(a.startAt))
    .map((m) => ({
      id: m.id,
      topic: m.topic,
      headline: m.minutes?.headline ?? null,
      startAt: m.startAt,
      mode: m.mode,
      status: m.status,
      attendees: s.members.map((x) => x.name),
      hasTranscript: m.transcript.length > 0,
      suggestionCount: s.suggestions.filter((g) => g.meetingId === m.id).length,
    }))
}

/**
 * 알림은 저장하지 않고 할 일·회의 상태에서 바로 만든다(시안10의 risks()).
 * 할 일만 바꾸면 알림·홈 종 숫자·뱃지가 함께 맞는다. ID는 상황마다 같게 만들어 읽음 처리가 유지된다.
 */
export function buildNotices(s: DemoState, viewer: Id, now: Dayjs): NoticeList {
  const read = new Set(s.readNotices[viewer] ?? [])
  const notices: Omit<Notice, 'read'>[] = []

  for (const t of liveTasks(s)) {
    const title = `'${t.title}'`
    const who = nameOf(s, t.assigneeId)
    const about = { taskId: t.id, taskTitle: t.title, meetingId: null }
    if (isLate(t, now) && t.dueDate) {
      const days = -daysUntil(t.dueDate, now)
      notices.push({
        id: `late-${t.id}-${t.dueDate}`, kind: '늦음', ...about,
        reason: `${title} 기한 ${withJosa(formatMD(t.dueDate), '이/가')} ${days}일 지났어요`,
        createdAt: dayjs(t.dueDate).add(1, 'day').hour(9).format(),
      })
    }
    if (t.status === '막힘') {
      const why = t.blockedReason ? ` "${t.blockedReason}"` : ''
      notices.push({
        id: `blocked-${t.id}`, kind: '막힘', ...about,
        reason: `${withJosa(who ?? '담당자', '이/가')} ${withJosa(title, '이/가')} 막혔다고 표시했어요.${why}`,
        createdAt: s.clockNow,
      })
    }
    if (t.status === '완료' && t.doneAt) {
      notices.push({
        id: `done-${t.id}-${t.doneAt}`, kind: '완료', ...about,
        reason: `${withJosa(who ?? '담당자', '이/가')} ${withJosa(title, '을/를')} 끝냈어요`,
        createdAt: t.doneAt,
      })
    }
  }

  for (const m of s.meetings) {
    const slot = `${formatSlot(m.startAt, m.endAt)} ${m.mode}`
    const about = { taskId: null, taskTitle: null, meetingId: m.id }
    const minutesToStart = dayjs(m.startAt).diff(now, 'minute')
    if (m.status === 'confirmed' && minutesToStart > 0 && minutesToStart <= 30) {
      const lastHeld = s.meetings.filter((x) => x.status === 'done').sort((a, b) => b.startAt.localeCompare(a.startAt))[0]
      const pendings = lastHeld?.minutes?.pendings.length ?? 0
      const left = liveTasks(s).filter((t) => t.status !== '완료').length
      notices.push({
        id: `soon-${m.id}`, kind: '회의 30분 전', ...about,
        reason: `'${m.topic}' ${formatTime(m.startAt)} 시작 · ${m.mode}. 지난 회의 보류 ${pendings}개, 남은 할 일 ${left}개를 다뤄요`,
        createdAt: dayjs(m.startAt).subtract(30, 'minute').format(),
      })
    }
    const p = s.proposals.find((x) => x.meetingId === m.id)
    if (p && m.status === 'proposed' && p.responses[viewer] === '대기') {
      notices.push({
        id: `proposed-${m.id}`, kind: '회의 제안', ...about,
        reason: `회의 일정이 나왔습니다. ${slot}. ${p.rationale}`,
        createdAt: s.agentLog.find((a) => a.what.startsWith('조율 결과'))?.at ?? s.clockNow,
      })
    }
    if (p && m.status === 'confirmed') {
      notices.push({
        id: `confirmed-${m.id}`, kind: '회의 확정', ...about,
        reason: `${withJosa(slot, '으로/로')} 확정됐어요. 모두 수락했어요`,
        createdAt: s.clockNow,
      })
    }
  }

  const order = (n: Omit<Notice, 'read'>) => NOTICE_KINDS.indexOf(n.kind)
  const sorted = notices
    .sort((a, b) => order(a) - order(b) || b.createdAt.localeCompare(a.createdAt))
    .map((n) => ({ ...n, read: read.has(n.id) }))
  return { notices: sorted, unreadCount: sorted.filter((n) => !n.read).length }
}

export function buildActivity(s: DemoState): ActivityLog {
  return {
    agentLog: [...s.agentLog].sort((a, b) => b.at.localeCompare(a.at)),
    yieldRecords: s.yieldRecords.map((y) => ({ ...y, name: nameOf(s, y.userId) ?? '' })),
  }
}
