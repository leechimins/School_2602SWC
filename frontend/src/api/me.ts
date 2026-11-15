import type { Id, IsoDate } from '../types/common.ts'
import type { LinkResult, MyWeek, Preferences, ScheduleItemInput, ScheduleItemPatch } from '../types/me.ts'
import { ApiError, request, write } from './client.ts'
import { toMyWeek, toPreferences, toServerPreferences, type ServerMySchedule, type ServerPreference } from './convert.ts'

// 내 조건(나 탭·온보딩): 조건 네 가지, 내 주간 시간표, 일정 연결. 화면은 이 함수들만 부른다.

const AI_TIMEOUT_MS = 25_000 // "피하고 싶은 시간"을 에이전트가 다듬느라 저장이 늦을 수 있다(서버 LLM 최대 20초)

export async function getPreferences(): Promise<Preferences> {
  return toPreferences(await request<ServerPreference>('/me/preferences'))
}

/** 조건 저장. 온보딩은 네 칸을 한꺼번에 덮어쓰고(POST), 나 화면은 고친 값을 보낸다(PATCH) */
export function savePreferences(prefs: Preferences, from: 'onboarding' | 'me'): Promise<Preferences> {
  const body = toServerPreferences(prefs)
  return write(async () =>
    toPreferences(
      await request<ServerPreference>(from === 'onboarding' ? '/me/onboarding/interpret' : '/me/preferences', {
        method: from === 'onboarding' ? 'POST' : 'PATCH',
        body,
        timeoutMs: AI_TIMEOUT_MS,
      }),
    ),
  )
}

/** 한 주(월~일) 내 시간표. anyDay는 그 주의 아무 날 */
export async function getMyWeek(roomId: Id, anyDay: IsoDate): Promise<MyWeek> {
  return toMyWeek(await request<ServerMySchedule>(`/rooms/${roomId}/me/schedule?week=${anyDay}`))
}

/** 일정 직접 추가(매주 반복). 내 수업과 겹치면 서버가 409(CLASS_CONFLICT) 문구를 준다 */
export function addScheduleItem(input: ScheduleItemInput): Promise<void> {
  return write(async () => {
    await request('/me/schedule/items', {
      method: 'POST',
      body: {
        title: input.title,
        kind: input.kind,
        days: input.days.map((d) => ({ weekday: d.weekday, start_min: d.startHour * 60, end_min: d.endHour * 60 })),
      },
    })
  })
}

// 서버에 고치기·지우기 API가 아직 없으면(404·405) "잠시 후 다시"가 아니라 못 한다고 알린다
const notEditable = (e: unknown) =>
  e instanceof ApiError && (e.status === 404 || e.status === 405)
    ? new ApiError(e.status, 'SCHEDULE_EDIT_UNAVAILABLE', '지금은 이 일정을 고칠 수 없어요. 일정 추가로 새로 넣어 주세요.')
    : e

/** 직접 넣은 일정 한 칸(요일 하나) 고치기. 나 탭 시간표에서 길게 눌러 연다 */
export function editScheduleItem(itemId: Id, patch: ScheduleItemPatch): Promise<void> {
  return write(async () => {
    await request(`/me/schedule/items/${itemId}`, {
      method: 'PATCH',
      body: { title: patch.title, start_min: patch.startHour * 60, end_min: patch.endHour * 60 },
    }).catch((e: unknown) => {
      throw notEditable(e)
    })
  })
}

/** 직접 넣은 일정 한 칸 지우기 */
export function deleteScheduleItem(itemId: Id): Promise<void> {
  return write(async () => {
    await request(`/me/schedule/items/${itemId}`, { method: 'DELETE' }).catch((e: unknown) => {
      throw notEditable(e)
    })
  })
}

type ServerIntegration = { imported_count: number }

/** 에브리타임 공유 링크로 수업 불러오기. 이미 연결돼 있으면 다시 불러온다 */
export function connectEverytime(url: string): Promise<LinkResult> {
  return write(async () => {
    // 브라우저로 공유 페이지를 열어 읽어서 몇 초 걸린다
    const r = await request<ServerIntegration>('/me/integrations/everytime', { method: 'POST', body: { url }, timeoutMs: 30_000 })
    return { count: r.imported_count }
  })
}

/**
 * 구글 캘린더 연결. 서버는 구글 팝업(Google Identity Services)에서 받은 코드를 받아야 하는데,
 * 프론트에 구글 캘린더 권한 팝업이 아직 없어 열지 않는다. 그동안은 직접 입력으로 이어 가라고 안내한다.
 */
export function connectGoogle(): Promise<LinkResult> {
  return Promise.reject(new ApiError(400, 'GOOGLE_NOT_READY', '지금은 구글 캘린더를 연결할 수 없어요. 시간표를 직접 넣어 주세요.'))
}
