import dayjs from 'dayjs'
import type { Id, MeetingMode } from '../types/common.ts'
import type { Home } from '../types/home.ts'
import { DAYPARTS, type MyWeek, type Preferences, type ScheduleSource, type WeekBlock } from '../types/me.ts'
import type {
  CoordinatingBrief,
  MeetingBrief,
  MeetingDetail,
  MeetingStatus,
  Minutes,
  Schedule,
  Suggestion,
} from '../types/meeting.ts'
import type { ActivityLog, Notice, NoticeKind, NoticeList } from '../types/notification.ts'
import type { Member, Room, YieldLevel } from '../types/room.ts'
import type { Burden, Proposal, ResponseState, Scheduling, SchedulingStatus, Utterance } from '../types/scheduling.ts'
import type { Task, TaskStatus, TeamTasks } from '../types/task.ts'

// 서버 응답(snake_case, 영문 코드) → 프론트 타입(camelCase, 화면 용어).
// 백엔드 응답 모양이 바뀌면 이 파일의 Server* 타입과 to* 함수만 고친다. 화면 코드는 그대로다.
// Server* 타입은 backend/app/*/schemas.py(11/6 main)를 옮긴 것이다.

// ── 코드 대응표 ─────────────────────────────────────────

type ServerMode = 'offline' | 'online' | 'any'
type ServerTaskState = 'todo' | 'doing' | 'blocked' | 'done'
type ServerResponse = 'pending' | 'accepted' | 'declined'
type ServerBurden = 'ok' | 'some' | 'much'
type ServerYield = 'none' | 'some' | 'much'

const MODE: Record<ServerMode, MeetingMode | '상관없음'> = { offline: '대면', online: '비대면', any: '상관없음' }
export const TASK_STATE: Record<ServerTaskState, TaskStatus> = { todo: '시작 전', doing: '진행 중', blocked: '막힘', done: '완료' }
const RESPONSE: Record<ServerResponse, ResponseState> = { pending: '대기', accepted: '수락', declined: '거절' }
const BURDEN: Record<ServerBurden, Burden> = { ok: '괜찮음', some: '조금', much: '많이' }
const YIELD: Record<ServerYield, YieldLevel> = { none: '아직 없음', some: '조금 맞춰 줌', much: '많이 맞춰 줌' }

/** 프론트 → 서버로 보낼 때 */
export const toServerState = (status: TaskStatus) =>
  (Object.keys(TASK_STATE) as ServerTaskState[]).find((k) => TASK_STATE[k] === status) ?? 'todo'
export const toServerMode = (mode: MeetingMode | '상관없음'): ServerMode =>
  mode === '대면' ? 'offline' : mode === '비대면' ? 'online' : 'any'

// 확정된 회의에는 any가 오지 않는다(DB CHECK)
const meetingMode = (m: ServerMode): MeetingMode => (m === 'offline' ? '대면' : '비대면')
const id = (n: number | string): Id => String(n)
const optId = (n: number | null | undefined): Id | null => (n == null ? null : String(n))

// ── 방 ──────────────────────────────────────────────────

export type ServerMember = {
  user_id: number
  name: string
  part: string | null
  is_leader: boolean
  is_me: boolean
  yield_level: ServerYield
}

export type ServerRoom = {
  id: number
  name: string
  description: string
  start_date: string
  due_date: string
  d_day: number
  eval_method: string
  member_count: number
  joined_count: number
  invite_code: string
  leader_user_id: number
  members: ServerMember[]
  can_start_scheduling: boolean
}

export const toMember = (m: ServerMember): Member => ({
  id: id(m.user_id),
  name: m.name,
  isLeader: m.is_leader,
  isMe: m.is_me,
  yieldLevel: YIELD[m.yield_level],
})

export const toRoom = (r: ServerRoom): Room => ({
  id: id(r.id),
  name: r.name,
  description: r.description,
  startDate: r.start_date,
  dueDate: r.due_date,
  inviteCode: r.invite_code,
  memberCount: r.member_count,
  joinedCount: r.joined_count,
  leaderId: id(r.leader_user_id),
  members: r.members.map(toMember),
  canStartScheduling: r.can_start_scheduling,
})

// ── 할 일 ───────────────────────────────────────────────

export type ServerTask = {
  id: number
  title: string
  due_date: string | null
  assignee_user_id: number | null
  assignee_name: string | null
  state: ServerTaskState
  source: { meeting_id: number; held_on: string; topic: string } | null
  confirmed_by_name: string | null
  confirmed_at: string | null
  is_late: boolean
  can_change_status: boolean
  can_edit: boolean
}

export type ServerTaskList = {
  tasks: ServerTask[]
  task_counts: { user_id: number; name: string; remaining: number }[]
  suggestion_count: number
}

export const toTask = (t: ServerTask): Task => ({
  id: id(t.id),
  title: t.title,
  dueDate: t.due_date,
  assigneeId: optId(t.assignee_user_id),
  assigneeName: t.assignee_name,
  status: TASK_STATE[t.state],
  blockedReason: null, // 서버가 아직 막힌 이유를 주지 않는다 (백엔드 요청 거리)
  source: t.source ? { meetingId: id(t.source.meeting_id), heldOn: t.source.held_on, topic: t.source.topic } : null,
  confirmedByName: t.confirmed_by_name,
  confirmedAt: t.confirmed_at,
  isLate: t.is_late,
  canChangeStatus: t.can_change_status,
  canEdit: t.can_edit,
})

export const toTeamTasks = (r: ServerTaskList): TeamTasks => ({
  tasks: r.tasks.map(toTask),
  counts: r.task_counts.map((c) => ({ userId: id(c.user_id), name: c.name, remaining: c.remaining })),
  suggestionCount: r.suggestion_count,
})

// ── 일정·회의 ───────────────────────────────────────────

export type ServerMeetingBrief = {
  id: number
  topic: string
  start_at: string
  end_at: string
  mode: ServerMode
  status: MeetingStatus
  settled: boolean
  my_state: ServerResponse | null
  pending_count: number
  suggestion_count?: number // 지난 회의 "제안 N개" (백엔드 요청 거리)
}

export type ServerCoordinatingBrief = {
  id: number
  topic: string
  window_start: string
  window_end: string
  status: SchedulingStatus
}

export type ServerSchedule = {
  coordinating: ServerCoordinatingBrief[]
  upcoming: ServerMeetingBrief[]
  past: ServerMeetingBrief[]
}

export const toMeetingBrief = (m: ServerMeetingBrief): MeetingBrief => ({
  id: id(m.id),
  topic: m.topic,
  startAt: m.start_at,
  endAt: m.end_at,
  mode: meetingMode(m.mode),
  status: m.status,
  settled: m.settled,
  myState: m.my_state ? RESPONSE[m.my_state] : null,
  pendingCount: m.pending_count,
  suggestionCount: m.suggestion_count ?? 0,
})

export const toCoordinating = (c: ServerCoordinatingBrief): CoordinatingBrief => ({
  id: id(c.id),
  topic: c.topic,
  windowStart: c.window_start,
  windowEnd: c.window_end,
  status: c.status,
})

export const toSchedule = (r: ServerSchedule): Schedule => ({
  coordinating: r.coordinating.map(toCoordinating),
  upcoming: r.upcoming.map(toMeetingBrief),
  past: r.past.map(toMeetingBrief),
})

// ── 홈 ──────────────────────────────────────────────────

type ServerHomeTask = {
  id: number
  title: string
  due_date: string | null
  state: ServerTaskState
  late: boolean
  blocked: boolean
}

export type ServerHome = {
  today: string
  start_date: string
  due_date: string
  d_day: number
  next_meeting: (Omit<ServerMeetingBrief, 'pending_count'> & { accepted: number; responders: number }) | null
  coordinating: ServerCoordinatingBrief | null
  my_tasks: ServerHomeTask[]
  unread_notifications: number
  can_start_scheduling: boolean
  invite_code: string
  joined_count: number
  member_count: number
}

/** 홈의 할 일은 짧은 모양으로 온다. 내 할 일이므로 담당자는 나, 상태는 내가 바꿀 수 있다 */
export const toHome = (r: ServerHome, roomName: string, me: { id: Id; name: string }): Home => ({
  roomName,
  today: r.today,
  startDate: r.start_date,
  dueDate: r.due_date,
  dDay: r.d_day,
  nextMeeting: r.next_meeting
    ? toMeetingBrief({ ...r.next_meeting, pending_count: r.next_meeting.responders - r.next_meeting.accepted })
    : null,
  coordinating: r.coordinating ? toCoordinating(r.coordinating) : null,
  myTasks: r.my_tasks.map((t) => ({
    id: id(t.id),
    title: t.title,
    dueDate: t.due_date,
    assigneeId: me.id,
    assigneeName: me.name,
    status: TASK_STATE[t.state],
    blockedReason: null,
    source: null,
    confirmedByName: null,
    confirmedAt: null,
    isLate: t.late,
    canChangeStatus: true,
    canEdit: true,
  })),
  unreadCount: r.unread_notifications,
  canStartScheduling: r.can_start_scheduling,
  inviteCode: r.invite_code,
  joinedCount: r.joined_count,
  memberCount: r.member_count,
})

// ── 조율 ────────────────────────────────────────────────

type ServerUtterance = {
  seq: number
  round_no: number
  speaker_kind: 'judge' | 'member'
  speaker_user_id: number | null
  speaker_name: string | null
  text: string
  created_at: string
}

export type ServerScheduling = {
  id: number
  topic: string
  window_start: string
  window_end: string
  duration_min: number
  mode: ServerMode
  status: SchedulingStatus
  rounds_used: number
  candidate_count: number
  meeting_id: number | null
  utterances: ServerUtterance[]
}

// 서버 발언에는 아직 text만 있다. 불편 단계·제안 시간은 백엔드 요청 거리라 비워 둔다.
// 어필/응답은 순서로 가른다: 한 라운드에서 판단 에이전트보다 먼저 나온 팀원 발언이 어필, 뒤에 나온 것이 수락·거절이다
const judgeSeqByRound = (us: ServerUtterance[]) =>
  new Map(us.filter((u) => u.speaker_kind === 'judge').map((u) => [u.round_no, u.seq]))

const toUtterance = (u: ServerUtterance, judgeSeq: Map<number, number>): Utterance => ({
  seq: u.seq,
  round: u.round_no,
  kind: u.speaker_kind === 'judge' ? 'judge' : u.seq < (judgeSeq.get(u.round_no) ?? Infinity) ? 'appeal' : 'answer',
  speakerId: optId(u.speaker_user_id),
  speakerName: u.speaker_name,
  text: u.text,
  answer: null,
  burden: null,
  myScore: null,
  slot: null,
  yieldChanges: [],
})

export const toScheduling = (r: ServerScheduling): Scheduling => {
  const judgeSeq = judgeSeqByRound(r.utterances)
  return {
    id: id(r.id),
    topic: r.topic,
    windowStart: r.window_start,
    windowEnd: r.window_end,
    durationMin: r.duration_min,
    mode: MODE[r.mode],
    status: r.status,
    roundsUsed: r.rounds_used,
    utterances: r.utterances.map((u) => toUtterance(u, judgeSeq)),
    proposalId: optId(r.meeting_id), // 합의·조정이 끝나야 생긴다
  }
}

export type ServerProposal = {
  id: number
  topic: string
  start_at: string
  end_at: string
  mode: ServerMode
  status: MeetingStatus
  rationale: string
  scheduling_status: SchedulingStatus | null
  my_score: number | null
  my_reason: string
  my_yield_points: number
  my_state: ServerResponse | null
  can_respond: boolean
  feedback_only: boolean
  responders: {
    user_id: number
    name: string
    state: ServerResponse
    burden: ServerBurden
    reason: string
    yield_level: ServerYield
    feedback: string | null
  }[]
}

export const toProposal = (r: ServerProposal): Proposal => ({
  id: id(r.id),
  schedulingId: null, // 회의 → 조율 ID (백엔드 요청 거리)
  roundsUsed: null,
  topic: r.topic,
  startAt: r.start_at,
  endAt: r.end_at,
  mode: meetingMode(r.mode),
  confirmed: r.status === 'confirmed',
  cancelled: r.status === 'cancelled',
  settled: r.scheduling_status === 'settled',
  rationale: r.rationale,
  myScore: r.my_score,
  myReason: r.my_reason,
  myYieldPoints: r.my_yield_points,
  myState: r.my_state ? RESPONSE[r.my_state] : null,
  canRespond: r.can_respond,
  feedbackOnly: r.feedback_only,
  absentName: null, // 불참안의 빠진 사람 (백엔드 요청 거리)
  responders: r.responders.map((x) => ({
    userId: id(x.user_id),
    name: x.name,
    state: RESPONSE[x.state],
    burden: BURDEN[x.burden],
    reason: x.reason,
    yieldLevel: YIELD[x.yield_level],
    feedback: x.feedback,
  })),
  yieldGetter: null, // 양보 점수 받는 사람의 단계 변화 (백엔드 요청 거리)
  myFeedback: null, // 남긴 말로 바뀐 선호 (백엔드 요청 거리)
})

// ── 회의록 ──────────────────────────────────────────────

type ServerMinutes = {
  headline: string
  status: Minutes['status']
  decisions: string[]
  discussions: string[]
  pendings: string[]
}

export type ServerSuggestion = {
  id: number
  title: string
  due_date: string | null
  assignee_user_id: number | null
  assignee_name: string | null
}

export type ServerMeetingDetail = {
  id: number
  topic: string
  start_at: string
  end_at: string
  mode: ServerMode
  status: MeetingStatus
  transcript_mode: 'stt' | 'manual' | null
  attendees: { user_id: number; name: string }[]
  transcript: { seq: number; speaker_user_id: number | null; speaker_name: string | null; text: string }[]
  minutes: ServerMinutes | null
  tasks: ServerTask[]
  done_tasks?: ServerTask[]
  suggestions: ServerSuggestion[]
}

export const toSuggestion = (g: ServerSuggestion): Suggestion => ({
  id: id(g.id),
  title: g.title,
  dueDate: g.due_date,
  assigneeId: optId(g.assignee_user_id),
  assigneeName: g.assignee_name,
})

export const toMeetingDetail = (r: ServerMeetingDetail): MeetingDetail => ({
  id: id(r.id),
  topic: r.topic,
  startAt: r.start_at,
  endAt: r.end_at,
  mode: meetingMode(r.mode),
  status: r.status,
  attendees: r.attendees.map((a) => a.name),
  transcript: r.transcript.map((l) => ({ seq: l.seq, speakerId: optId(l.speaker_user_id), speakerName: l.speaker_name, text: l.text })),
  minutes: r.minutes,
  tasks: r.tasks.map(toTask),
  doneTasks: (r.done_tasks ?? []).map(toTask), // "회의에서 끝난 일". 진행 중으로 되돌리면 서버가 목록에서 뺀다
  suggestions: r.suggestions.map(toSuggestion),
  unneededTasks: [], // 서버에 없는 목록(AI가 고르지 않는다). 실서버에서는 이 칸이 안 보인다
})

// ── 에이전트가 한 일 · 양보 기록 ─────────────────────────────
// backend/app/notice/router.py의 ActivityOut(GET /rooms/{id}/agent-log). 둘 다 최신순으로 온다

export type ServerActivity = {
  agent_log: { id: number; at: string; what: string; why: string }[]
  yield_records: { id: number; meeting_label: string; user_id: number; name: string; why: string }[]
}

export const toActivity = (r: ServerActivity): ActivityLog => ({
  agentLog: r.agent_log.map((a) => ({ id: id(a.id), at: a.at, what: a.what, why: a.why })),
  yieldRecords: r.yield_records.map((y) => ({
    id: id(y.id),
    meetingLabel: y.meeting_label,
    userId: id(y.user_id),
    name: y.name,
    why: y.why,
  })),
})

// ── 알림 ────────────────────────────────────────────────
// 알림 응답 스키마는 아직 서버에 없다. NotificationKind(shared/enums.py)와 api-스펙을 보고 잡은 모양이라 나오면 맞춘다.

type ServerNoticeKind = 'late' | 'blocked' | 'done' | 'meeting_soon' | 'meeting_proposed' | 'meeting_confirmed'

const NOTICE_KIND: Record<ServerNoticeKind, NoticeKind> = {
  late: '늦음',
  blocked: '막힘',
  done: '완료',
  meeting_soon: '회의 30분 전',
  meeting_proposed: '회의 제안',
  meeting_confirmed: '회의 확정',
}

// backend/app/notice/router.py의 NotificationListOut. 읽음은 시각(read_at)으로 오고, 할 일 제목은 reason 안에 이미 있다
export type ServerNoticeList = {
  items: {
    id: number
    kind: ServerNoticeKind
    reason: string
    task_id: number | null
    meeting_id: number | null
    read_at: string | null
    created_at: string
  }[]
  unread_count: number
}

export const toNoticeList = (r: ServerNoticeList): NoticeList => ({
  notices: r.items.map(
    (n): Notice => ({
      id: id(n.id),
      kind: NOTICE_KIND[n.kind],
      reason: n.reason,
      taskId: optId(n.task_id),
      taskTitle: null, // 서버가 따로 주지 않는다. 카드 문구(reason)에 제목이 들어 있다
      meetingId: optId(n.meeting_id),
      createdAt: n.created_at,
      read: n.read_at !== null,
    }),
  ),
  unreadCount: r.unread_count,
})

// ── 내 조건(선호·주간 시간표) ─────────────────────────────

type ServerDaypart = 'morning' | 'forenoon' | 'lunch' | 'afternoon' | 'evening' | 'night'
const SERVER_DAYPARTS: ServerDaypart[] = ['morning', 'forenoon', 'lunch', 'afternoon', 'evening', 'night'] // DAYPARTS와 같은 순서

/** 서버 시각 피커 한 칸: 숫자 + 오전·오후 (backend/app/me/schemas.py Hour12) */
type ServerHour12 = { hour12: number; ampm: 'am' | 'pm'; minute: 0 | 30 }

export type ServerPreference = {
  day_start_min: number | null
  day_end_min: number | null
  mode_pref: ServerMode | null
  dayparts: ServerDaypart[] | null
  avoid_raw: string | null
}

export const toPreferences = (r: ServerPreference): Preferences => ({
  fromHour: r.day_start_min === null ? null : Math.floor(r.day_start_min / 60),
  toHour: r.day_end_min === null ? null : Math.floor(r.day_end_min / 60),
  mode: r.mode_pref === null ? null : (MODE[r.mode_pref] as Preferences['mode']),
  dayparts: (r.dayparts ?? []).map((d) => DAYPARTS[SERVER_DAYPARTS.indexOf(d)]),
  avoid: r.avoid_raw ?? '',
})

const toHour12 = (hour: number): ServerHour12 => ({ hour12: hour % 12 || 12, ampm: hour < 12 ? 'am' : 'pm', minute: 0 })

/** 온보딩·내 조건 저장 body. 비운 칸은 null(지운다) */
export const toServerPreferences = (p: Preferences) => ({
  day_start: p.fromHour === null ? null : toHour12(p.fromHour),
  day_end: p.toHour === null ? null : toHour12(p.toHour),
  mode_pref: p.mode === null ? null : toServerMode(p.mode),
  dayparts: p.dayparts.map((d) => SERVER_DAYPARTS[DAYPARTS.indexOf(d)]),
  avoid_raw: p.avoid.trim() || null,
})

export type ServerMySchedule = {
  week_start: string
  week_end: string
  items: {
    kind: 'class' | 'event' | 'meeting'
    title: string | null
    start_at: string
    end_at: string
    source: ScheduleSource | null
    meeting_status: MeetingStatus | null
  }[]
}

const hourOf = (iso: string) => {
  const t = dayjs(iso)
  return t.hour() + t.minute() / 60
}

export const toMyWeek = (r: ServerMySchedule): MyWeek => ({
  weekStart: r.week_start,
  weekEnd: r.week_end,
  blocks: r.items.map((i): WeekBlock => {
    const waiting = i.kind === 'meeting' && i.meeting_status === 'proposed'
    return {
      kind: waiting ? 'waiting' : i.kind,
      title: i.kind === 'meeting' ? (waiting ? '회의 대기' : '팀 회의') : (i.title ?? '일정'),
      weekday: (dayjs(i.start_at).day() + 6) % 7,
      startHour: hourOf(i.start_at),
      // 자정을 넘기는 칸은 그날 끝(24시)까지만 그린다
      endHour: dayjs(i.end_at).isSame(dayjs(i.start_at), 'day') ? hourOf(i.end_at) : 24,
      source: i.source,
    }
  }),
})
