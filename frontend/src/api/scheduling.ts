import { UTTERANCE_MS, later } from '../lib/timers.ts'
import { mockContext } from '../mock/context.ts'
import { dispatch } from '../mock/store.ts'
import { buildProposal, buildSchedule, buildScheduling } from '../mock/views.ts'
import type { Id } from '../types/common.ts'
import type { Schedule } from '../types/meeting.ts'
import type { Proposal, RespondInput, Scheduling, SchedulingInput } from '../types/scheduling.ts'
import { ApiError, request, withMock, withMockWrite } from './client.ts'
import {
  toProposal,
  toSchedule,
  toScheduling,
  toServerMode,
  type ServerProposal,
  type ServerSchedule,
  type ServerScheduling,
} from './convert.ts'

// 회의 잡기(조율)와 일정. 장면 1의 데이터가 모두 여기서 나온다.

/**
 * 조율 시작 (팀장만). 목 모드에서는 준비된 조율 대본을 다시 돌린다:
 * 바로 "진행 중" 조율을 돌려주고, 화면이 발언을 다 보여 줄 즈음 서버처럼 조율을 끝내 회의안을 낸다.
 */
export function startScheduling(roomId: Id, input: SchedulingInput): Promise<Scheduling> {
  return withMockWrite(
    async () =>
      toScheduling(
        await request<ServerScheduling>(`/rooms/${roomId}/schedulings`, {
          method: 'POST',
          body: {
            topic: input.topic,
            // 서버는 오프셋 붙은 시각만 받는다(api-스펙 권장 규칙 2). 날짜를 그날 처음·끝으로 — 목(actions.ts)과 같은 규칙
            window_start: `${input.windowStart}T00:00:00+09:00`,
            window_end: `${input.windowEnd}T23:59:00+09:00`,
            duration_min: input.durationMin,
            mode: toServerMode(input.mode),
          },
        }),
      ),
    () => {
      // 서버와 같은 거절 (meeting/router.py start)
      const before = mockContext()
      if (before.viewer !== before.s.room.leaderId) throw new ApiError(403, 'FORBIDDEN', '조율은 팀장만 시작할 수 있습니다.')
      if (before.s.meetings.some((m) => m.status === 'proposed')) {
        throw new ApiError(409, 'AWAITING_RESPONSE', '수락을 기다리는 회의가 있어요. 모두 답한 뒤에 다시 시작해 주세요.')
      }
      if (before.s.schedulings.some((c) => c.status === 'running')) throw new ApiError(409, 'ALREADY_RUNNING', '이미 진행 중인 조율이 있습니다.')
      dispatch({ type: 'scheduling/start', input })
      const { s, viewer } = mockContext()
      const started = s.schedulings[s.schedulings.length - 1]
      later(() => dispatch({ type: 'scheduling/finish', schedulingId: started.id }), (started.script.length - 1) * UTTERANCE_MS)
      return buildScheduling(s, started.id, viewer)
    },
  )
}

/** 지금까지의 조율: 발언 목록을 한 번에 받아 화면이 하나씩 보여 준다 */
export function getScheduling(roomId: Id, schedulingId: Id): Promise<Scheduling> {
  return withMock(
    async () => toScheduling(await request<ServerScheduling>(`/rooms/${roomId}/schedulings/${schedulingId}`)),
    () => {
      const { s, viewer } = mockContext()
      return buildScheduling(s, schedulingId, viewer)
    },
  )
}

/** 회의 일정 조율 확인: 보는 사람마다 내 불편·양보 점수가 다르다 */
export function getProposal(roomId: Id, proposalId: Id): Promise<Proposal> {
  return withMock(
    async () => toProposal(await request<ServerProposal>(`/rooms/${roomId}/proposals/${proposalId}`)),
    () => {
      const { s, viewer } = mockContext()
      return buildProposal(s, proposalId, viewer)
    },
  )
}

/**
 * 수락·거절 + 피드백 한 줄. 전원 수락하면 회의가 자동으로 확정된다.
 * 거절하면 라운드가 남았을 때 서버가 바로 다시 조율하고, 3라운드를 다 썼으면 거절한 사람을 불참으로 둔다.
 * 목 모드에서는 다시 도는 조율을 시작할 때처럼 발언을 다 보여 줄 즈음 끝낸다.
 */
export function respondProposal(roomId: Id, proposalId: Id, input: RespondInput): Promise<void> {
  return withMockWrite(
    () => request<void>(`/rooms/${roomId}/proposals/${proposalId}/respond`, { method: 'POST', body: input }),
    () => {
      // 서버와 같은 거절 (meeting/router.py respond)
      const before = mockContext()
      const proposal = before.s.proposals.find((p) => p.meetingId === proposalId)
      const meeting = before.s.meetings.find((m) => m.id === proposalId)
      if (proposal?.responses[before.viewer] === undefined) throw new ApiError(403, 'FORBIDDEN', '이 회의에 답할 사람이 아닙니다.')
      if (meeting?.status !== 'proposed' && meeting?.status !== 'confirmed') throw new ApiError(409, 'CLOSED', '끝난 회의입니다.')
      dispatch({ type: 'proposal/respond', meetingId: proposalId, userId: before.viewer, ...input })
      const { s } = mockContext()
      const schedulingId = s.proposals.find((p) => p.meetingId === proposalId)?.schedulingId
      const rerun = s.schedulings.find((c) => c.id === schedulingId && c.status === 'running')
      if (rerun) later(() => dispatch({ type: 'scheduling/finish', schedulingId: rerun.id }), (rerun.script.length - 1) * UTTERANCE_MS)
    },
  )
}

/** 남긴 말로 바뀐 선호 되돌리기. 서버에 아직 없는 동작이라 목 데이터만 바꾼다 */
export function undoFeedbackChange(proposalId: Id): Promise<void> {
  dispatch({ type: 'feedback/undo', meetingId: proposalId, userId: mockContext().viewer })
  return Promise.resolve()
}

/** 일정 탭: 조율 중 → 잡힌 회의 → 지난 회의 */
export function getSchedule(roomId: Id): Promise<Schedule> {
  return withMock(
    async () => toSchedule(await request<ServerSchedule>(`/rooms/${roomId}/schedule`)),
    () => {
      const { s, viewer, now } = mockContext()
      return buildSchedule(s, viewer, now)
    },
  )
}
