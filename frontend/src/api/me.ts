import { mockContext } from '../mock/context.ts'
import { DEMO_EVERYTIME_CLASSES, DEMO_GOOGLE_EVENTS } from '../mock/seed.ts'
import { dispatch } from '../mock/store.ts'
import { buildMyWeek } from '../mock/views.ts'
import type { Id, IsoDate } from '../types/common.ts'
import type { LinkResult, MyWeek, Preferences, ScheduleItemInput, ScheduleItemPatch } from '../types/me.ts'
import { ApiError, request, withMock, withMockWrite } from './client.ts'
import { toMyWeek, toPreferences, toServerPreferences, type ServerMySchedule, type ServerPreference } from './convert.ts'

// 내 조건(나 탭·온보딩): 조건 네 가지, 내 주간 시간표, 일정 연결. 화면은 이 함수들만 부른다.

const EMPTY_PREFS: Preferences = { fromHour: null, toHour: null, mode: null, dayparts: [], avoid: '' }
const AI_TIMEOUT_MS = 25_000 // "피하고 싶은 시간"을 에이전트가 다듬느라 저장이 늦을 수 있다(서버 LLM 최대 20초)

export function getPreferences(): Promise<Preferences> {
  return withMock(
    async () => toPreferences(await request<ServerPreference>('/me/preferences')),
    () => {
      const { s, viewer } = mockContext()
      return s.prefs[viewer] ?? EMPTY_PREFS
    },
  )
}

/** 조건 저장. 온보딩은 네 칸을 한꺼번에 덮어쓰고(POST), 나 화면은 고친 값을 보낸다(PATCH) */
export function savePreferences(prefs: Preferences, from: 'onboarding' | 'me'): Promise<Preferences> {
  const body = toServerPreferences(prefs)
  return withMockWrite(
    async () =>
      toPreferences(
        await request<ServerPreference>(from === 'onboarding' ? '/me/onboarding/interpret' : '/me/preferences', {
          method: from === 'onboarding' ? 'POST' : 'PATCH',
          body,
          timeoutMs: AI_TIMEOUT_MS,
        }),
      ),
    () => {
      dispatch({ type: 'me/prefs', userId: mockContext().viewer, prefs })
      return prefs
    },
  )
}

/** 한 주(월~일) 내 시간표. anyDay는 그 주의 아무 날 */
export function getMyWeek(roomId: Id, anyDay: IsoDate): Promise<MyWeek> {
  return withMock(
    async () => toMyWeek(await request<ServerMySchedule>(`/rooms/${roomId}/me/schedule?week=${anyDay}`)),
    () => {
      const { s, viewer } = mockContext()
      return buildMyWeek(s, viewer, anyDay)
    },
  )
}

const CLASS_CONFLICT = new ApiError(409, 'CLASS_CONFLICT', '이미 수업이 있습니다.')

/** 일정 직접 추가(매주 반복). 내 수업과 겹치면 409 — 수업은 에브리타임에서 오는 고정된 시간이라 그쪽이 맞다 */
export function addScheduleItem(input: ScheduleItemInput): Promise<void> {
  return withMockWrite(
    async () => {
      await request('/me/schedule/items', {
        method: 'POST',
        body: {
          title: input.title,
          kind: input.kind,
          days: input.days.map((d) => ({ weekday: d.weekday, start_min: d.startHour * 60, end_min: d.endHour * 60 })),
        },
      })
    },
    () => {
      const { s, viewer } = mockContext()
      const classes = s.scheduleItems.filter((i) => i.userId === viewer && i.kind === 'class')
      const overlaps = input.days.some((d) =>
        classes.some((c) => c.weekday === d.weekday && d.startHour * 60 < c.endMin && c.startMin < d.endHour * 60),
      )
      if (overlaps) throw CLASS_CONFLICT
      dispatch({ type: 'me/schedule-add', userId: viewer, input })
    },
  )
}

/**
 * 직접 넣은 일정 한 칸(요일 하나) 고치기. 나 탭 시간표에서 길게 눌러 연다.
 * 실서버 PATCH /me/schedule/items/{id}는 백엔드 요청 중이다(GET 응답의 item_id가 이 용도). 없으면 서버 안내 문구가 그대로 보인다
 */
export function editScheduleItem(itemId: Id, patch: ScheduleItemPatch): Promise<void> {
  return withMockWrite(
    async () => {
      await request(`/me/schedule/items/${itemId}`, {
        method: 'PATCH',
        body: { title: patch.title, start_min: patch.startHour * 60, end_min: patch.endHour * 60 },
      })
    },
    () => dispatch({ type: 'me/schedule-edit', itemId, patch }),
  )
}

/** 직접 넣은 일정 한 칸 지우기. 실서버 DELETE /me/schedule/items/{id}도 백엔드 요청 중 */
export function deleteScheduleItem(itemId: Id): Promise<void> {
  return withMockWrite(
    async () => {
      await request(`/me/schedule/items/${itemId}`, { method: 'DELETE' })
    },
    () => dispatch({ type: 'me/schedule-delete', itemId }),
  )
}

type ServerIntegration = { imported_count: number }

/** 에브리타임 공유 링크로 수업 불러오기. 이미 연결돼 있으면 다시 불러온다 */
export function connectEverytime(url: string): Promise<LinkResult> {
  return withMockWrite(
    async () => {
      // 브라우저로 공유 페이지를 열어 읽어서 몇 초 걸린다
      const r = await request<ServerIntegration>('/me/integrations/everytime', { method: 'POST', body: { url }, timeoutMs: 30_000 })
      return { count: r.imported_count }
    },
    () => {
      if (!/everytime\.kr\/@[\w.-]+/.test(url)) {
        throw new ApiError(400, 'EVERYTIME_LINK_INVALID', '링크를 읽지 못했어요. 직접 입력해 주세요.')
      }
      dispatch({ type: 'me/everytime', userId: mockContext().viewer })
      return { count: DEMO_EVERYTIME_CLASSES.length }
    },
  )
}

/**
 * 구글 캘린더 연결. 실서버는 구글 팝업(Google Identity Services)에서 받은 코드를 보내야 하는데,
 * 프론트에 구글 클라이언트 ID가 아직 없어 팝업을 열지 않는다. 그동안은 직접 입력으로 이어 가라고 안내한다.
 */
export function connectGoogle(): Promise<LinkResult> {
  return withMockWrite(
    async () => {
      throw new ApiError(400, 'GOOGLE_NOT_READY', '지금은 구글 캘린더를 연결할 수 없어요. 시간표를 직접 넣어 주세요.')
    },
    () => {
      dispatch({ type: 'me/google', userId: mockContext().viewer })
      return { count: DEMO_GOOGLE_EVENTS.length }
    },
  )
}
