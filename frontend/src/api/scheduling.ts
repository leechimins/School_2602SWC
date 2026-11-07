import { UTTERANCE_MS, later } from '../lib/timers.ts'
import { mockContext } from '../mock/context.ts'
import { dispatch } from '../mock/store.ts'
import { buildProposal, buildSchedule, buildScheduling } from '../mock/views.ts'
import type { Id } from '../types/common.ts'
import type { Schedule } from '../types/meeting.ts'
import type { Proposal, RespondInput, Scheduling, SchedulingInput } from '../types/scheduling.ts'
import { request, withMock, withMockWrite } from './client.ts'
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
            window_start: input.windowStart,
            window_end: input.windowEnd,
            duration_min: input.durationMin,
            mode: toServerMode(input.mode),
          },
        }),
      ),
    () => {
      dispatch({ type: 'scheduling/start', input })
      const { s, viewer } = mockContext()
      const started = s.schedulings[s.schedulings.length - 1]
      later(() => dispatch({ type: 'scheduling/finish', schedulingId: started.id }), started.script.length * UTTERANCE_MS)
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

/** 수락·거절 + 피드백 한 줄. 전원 수락하면 회의가 자동으로 확정된다 */
export function respondProposal(roomId: Id, proposalId: Id, input: RespondInput): Promise<void> {
  return withMockWrite(
    () => request<void>(`/rooms/${roomId}/proposals/${proposalId}/respond`, { method: 'POST', body: input }),
    () => {
      const { viewer } = mockContext()
      dispatch({ type: 'proposal/respond', meetingId: proposalId, userId: viewer, ...input })
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
