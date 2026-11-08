import dayjs, { type Dayjs } from 'dayjs'
import { daysUntil, toIsoDate } from '../lib/date.ts'
import { withJosa } from '../lib/korean.ts'
import type { Id } from '../types/common.ts'
import type { Home } from '../types/home.ts'
import type { MyWeek, WeekBlock } from '../types/me.ts'
import type { CoordinatingBrief, MeetingBrief, MeetingDetail, Schedule } from '../types/meeting.ts'
import type { ActivityLog, NoticeList } from '../types/notification.ts'
import type { Room } from '../types/room.ts'
import type { Burden, Proposal, Scheduling, Utterance } from '../types/scheduling.ts'
import type { Task, TeamTasks } from '../types/task.ts'
import { isLate, nextYieldLevel, roundsUsed, yieldLevelOf, yieldPointsOf } from './actions.ts'
import type { DemoState, SeedMeeting, SeedTask } from './seed.ts'

// 목 데이터(원본) → 화면이 받는 모양. 서버가 할 일을 대신한다:
// 보는 사람(viewer)마다 다른 값(내 점수, can_*), 시연 시계(now) 기준 판정(늦음)을 여기서 만든다.
// 규칙(정렬·권한·빈 칸)은 서버 라우터와 api/convert.ts를 거친 결과와 같게 맞춘다. 근거가 되는 서버 파일을 함수마다 적어 둔다.
// 남의 불편 점수는 숫자로 내보내지 않는다(브리프 "내부 숫자는 보이지 않습니다").

const NOT_FOUND = (what: string) => new Error(`${withJosa(what, '을/를')} 찾을 수 없어요`)

/** 불편 점수 → 남에게 보이는 단계: 1점 괜찮음, 2~3점 조금, 4~5점 많이 */
export function burdenOf(score: number): Burden {
  if (score <= 1) return '괜찮음'
  return score <= 3 ? '조금' : '많이'
}

const nameOf = (s: DemoState, id: Id | null) => s.members.find((m) => m.id === id)?.name ?? null
const liveTasks = (s: DemoState) => s.tasks.filter((t) => !t.dismissed)

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
    confirmedAt: t.confirmedAt,
    isLate: isLate(t, now),
    canChangeStatus: t.assigneeId === null || t.assigneeId === viewer, // 담당자만, 담당자가 없으면 전원 (minutes/tasks.py)
    canEdit: true,
  }
}

/** 기한 순, 기한 없는 것은 맨 뒤 (minutes/tasks.py _due_key) */
const byDue = (a: Task, b: Task) => (a.dueDate ?? '9999').localeCompare(b.dueDate ?? '9999')

/** 팀 할 일 순서: 담당자 없음 → 나 → 다른 사람(사람별로 모아서). 묶음 안은 기한 순 (minutes/tasks.py team_order) */
function teamOrder(s: DemoState, viewer: Id) {
  const rank = (t: Task) =>
    t.assigneeId === null ? -2 : t.assigneeId === viewer ? -1 : s.members.findIndex((m) => m.id === t.assigneeId)
  return (a: Task, b: Task) => rank(a) - rank(b) || byDue(a, b)
}

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
      yieldLevel: yieldLevelOf(m.yieldTotal),
    })),
    canStartScheduling: viewer === room.leaderId,
  }
}

export function buildTeamTasks(s: DemoState, viewer: Id, now: Dayjs): TeamTasks {
  const tasks = liveTasks(s).map((t) => toTask(s, t, viewer, now)).sort(teamOrder(s, viewer))
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

/**
 * 홈의 내 할 일 (home/router.py _my_tasks): 늦음 → 오늘 → 내일 → 그 뒤 → 완료 순, 묶음 안은 기한 순.
 * 서버 홈은 짧은 모양으로 와서 출처·확정한 사람·막힌 이유가 비어 있다(api/convert.ts toHome)
 */
function buildHomeTasks(s: DemoState, viewer: Id, now: Dayjs): Task[] {
  const bucket = (t: Task) => {
    if (t.status === '완료') return 4
    if (t.dueDate === null) return 3
    const days = daysUntil(t.dueDate, now)
    return days < 0 ? 0 : days === 0 ? 1 : days === 1 ? 2 : 3
  }
  return liveTasks(s)
    .filter((t) => t.assigneeId === viewer)
    .map((t): Task => ({ ...toTask(s, t, viewer, now), blockedReason: null, source: null, confirmedByName: null, confirmedAt: null }))
    .sort((a, b) => bucket(a) - bucket(b) || byDue(a, b))
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
    suggestionCount: 0, // 서버 일정 응답에 아직 없다(api/convert.ts). 실서버와 같게 "제안 N개"를 띄우지 않는다
  }
}

/** 끝난 시각으로 가른다. 회의 중인 것은 아직 다가오는 것이다 (meeting/router.py schedule) */
const isUpcoming = (m: SeedMeeting, now: Dayjs) =>
  (m.status === 'proposed' || m.status === 'confirmed') && !dayjs(m.endAt).isBefore(now)

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
  const next = schedule.upcoming[0]
  const responses = Object.values(s.proposals.find((p) => p.meetingId === next?.id)?.responses ?? {})
  return {
    roomName: s.room.name,
    today: toIsoDate(now),
    startDate: s.room.startDate,
    dueDate: s.room.dueDate,
    dDay: daysUntil(s.room.dueDate, now),
    // 홈의 다음 회의는 "응답할 사람 − 수락한 사람"을 남은 수로 쓴다(api/convert.ts toHome). 거절한 사람도 남은 수에 든다
    nextMeeting: next ? { ...next, pendingCount: responses.length - responses.filter((r) => r === '수락').length } : null,
    coordinating: schedule.coordinating[0] ?? null,
    myTasks: buildHomeTasks(s, viewer, now),
    unreadCount: buildNotices(s, viewer).unreadCount,
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
    roundsUsed: roundsUsed(c),
    utterances,
    proposalId: c.meetingId,
  }
}

export function buildProposal(s: DemoState, meetingId: Id, viewer: Id): Proposal {
  const m = s.meetings.find((x) => x.id === meetingId)
  const p = s.proposals.find((x) => x.meetingId === meetingId)
  if (!m || !p) throw NOT_FOUND('회의')
  const c = s.schedulings.find((x) => x.id === p.schedulingId)
  const mine = p.burdens.find((b) => b.userId === viewer) // 조율 없이 잡힌 회의면 점수가 없다
  const myState = p.responses[viewer] ?? null // 응답할 사람이 아니면(불참안에서 빠진 사람) null
  const getter = p.burdens.find((b) => b.userId === p.gets)
  return {
    id: m.id,
    schedulingId: c?.id ?? null,
    roundsUsed: c ? roundsUsed(c) : null,
    topic: m.topic,
    startAt: m.startAt,
    endAt: m.endAt,
    mode: m.mode,
    // 회의안 화면 규칙은 meeting/router.py read_proposal
    confirmed: m.status === 'confirmed',
    cancelled: m.status === 'cancelled',
    settled: p.settled,
    rationale: p.rationale,
    myScore: mine?.score ?? null,
    myReason: mine?.reason ?? '',
    myYieldPoints: mine ? yieldPointsOf(mine.score) : 0, // 받는 사람이 누구든 내 불편만큼 (scorer.yield_points)
    myState,
    canRespond: myState === '대기' && m.status === 'proposed',
    feedbackOnly: myState !== null && m.status === 'confirmed', // 조정안이든 전원 수락이든 확정된 회의에는 한 줄만 남긴다
    absentName: nameOf(s, p.absent),
    // 응답할 사람 전원. 점수가 없으면(조율 없이 잡힌 회의) 괜찮음, 이유는 빈 칸
    responders: Object.entries(p.responses).map(([userId, state]) => {
      const cost = p.burdens.find((b) => b.userId === userId)
      return {
        userId,
        name: nameOf(s, userId) ?? '',
        state,
        burden: burdenOf(cost?.score ?? 1),
        reason: cost?.reason ?? '',
        yieldLevel: yieldLevelOf(s.members.find((x) => x.id === userId)?.yieldTotal ?? 0),
        feedback: p.feedback[userId]?.text ?? null,
      }
    }),
    yieldGetter: getter
      ? {
          userId: getter.userId,
          name: nameOf(s, getter.userId) ?? '',
          isMe: getter.userId === viewer,
          burden: burdenOf(getter.score),
          from: p.getsFrom,
          to: nextYieldLevel(p.getsFrom),
        }
      : null,
    myFeedback: p.feedback[viewer] ?? null,
  }
}

export function buildMeetingDetail(s: DemoState, meetingId: Id, viewer: Id, now: Dayjs): MeetingDetail {
  const m = s.meetings.find((x) => x.id === meetingId)
  if (!m) throw NOT_FOUND('회의')
  // 참석자 = 수락한 사람(minutes/record.py _attendees). 응답 없이 바로 기록한 회의는 비어 있다
  const p = s.proposals.find((x) => x.meetingId === m.id)
  const attendeeIds = p ? Object.keys(p.responses).filter((id) => p.responses[id] === '수락') : []
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
    doneTasks: liveTasks(s).filter((t) => t.doneMeetingId === m.id).map((t) => toTask(s, t, viewer, now)),
    suggestions: s.suggestions
      .filter((g) => g.meetingId === m.id)
      .map((g) => ({ id: g.id, title: g.title, dueDate: g.dueDate, assigneeId: g.assigneeId, assigneeName: nameOf(s, g.assigneeId) })),
    unneededTasks: liveTasks(s).flatMap((t) =>
      t.unneeded?.meetingId === m.id ? [{ task: toTask(s, t, viewer, now), why: t.unneeded.why, kept: t.unneeded.kept }] : [],
    ),
  }
}

/** 내 알림만, 최신순. 읽은 것도 같이 준다 (notice/router.py list_notifications). 할 일 제목은 reason 안에 있다 */
export function buildNotices(s: DemoState, viewer: Id): NoticeList {
  const notices = s.notices
    .filter((n) => n.userId === viewer)
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt) || b.seq - a.seq)
    .map(({ id, kind, reason, taskId, meetingId, createdAt, read }) => ({ id, kind, reason, taskId, taskTitle: null, meetingId, createdAt, read }))
  return { notices, unreadCount: notices.filter((n) => !n.read).length }
}

export function buildActivity(s: DemoState): ActivityLog {
  return {
    agentLog: [...s.agentLog].sort((a, b) => b.at.localeCompare(a.at)),
    yieldRecords: s.yieldRecords.map((y) => ({ ...y, name: nameOf(s, y.userId) ?? '' })),
  }
}

/**
 * 내 한 주(월~일) 시간표: 내 일정(매주 반복) + 내가 응답할 사람이고 거절하지 않은 팀 회의.
 * 서버 GET /rooms/{id}/me/schedule과 같은 규칙이다(응답 없이 바로 기록한 회의는 안 나온다). 팀 회의는 확정 대기면 waiting.
 */
export function buildMyWeek(s: DemoState, viewer: Id, anyDay: string): MyWeek {
  const monday = dayjs(anyDay).startOf('day').subtract((dayjs(anyDay).day() + 6) % 7, 'day')
  const sunday = monday.add(6, 'day')
  const mine: WeekBlock[] = s.scheduleItems
    .filter((i) => i.userId === viewer)
    .map((i) => ({
      kind: i.kind,
      title: i.title ?? '일정',
      weekday: i.weekday,
      startHour: i.startMin / 60,
      endHour: i.endMin / 60,
      source: i.source,
      itemId: i.id,
    }))
  const meetings: WeekBlock[] = s.meetings
    .filter((m) => m.status !== 'cancelled')
    .filter((m) => !dayjs(m.startAt).isBefore(monday) && dayjs(m.startAt).isBefore(sunday.add(1, 'day')))
    .filter((m) => {
      const mine = s.proposals.find((p) => p.meetingId === m.id)?.responses[viewer]
      return mine !== undefined && mine !== '거절'
    })
    .map((m) => {
      const start = dayjs(m.startAt)
      const end = dayjs(m.endAt)
      return {
        kind: m.status === 'proposed' ? 'waiting' : 'meeting',
        title: m.status === 'proposed' ? '회의 대기' : '팀 회의',
        weekday: (start.day() + 6) % 7,
        startHour: start.hour() + start.minute() / 60,
        endHour: end.hour() + end.minute() / 60,
        source: null,
        itemId: null,
      }
    })
  return { weekStart: toIsoDate(monday), weekEnd: toIsoDate(sunday), blocks: [...mine, ...meetings] }
}
