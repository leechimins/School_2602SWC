import type { Id, IsoDate } from '../types/common.ts'
import type { LinkResult, MyWeek, Preferences, ScheduleItemInput, ScheduleItemPatch, TermState } from '../types/me.ts'
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

// 시각은 오프셋을 붙여 보낸다(api-스펙 권장 규칙 2). 시는 0.5 단위라 분으로 바꾼다
const atKst = (date: string, hour: number) =>
  `${date}T${String(Math.floor(hour)).padStart(2, '0')}:${hour % 1 ? '30' : '00'}:00+09:00`

/**
 * 일정 직접 추가. 매주 반복과 한 번만이 같은 주소로 가고 recurrence로 나뉜다(백엔드 Recurrence와 같은 값).
 * 내 수업과 겹치면 서버가 409(CLASS_CONFLICT) 문구를 준다
 */
export function addScheduleItem(input: ScheduleItemInput): Promise<void> {
  const body =
    input.recurrence === 'weekly'
      ? {
          recurrence: 'weekly',
          title: input.title,
          kind: input.kind,
          days: input.days.map((d) => ({ weekday: d.weekday, start_min: d.startHour * 60, end_min: d.endHour * 60 })),
        }
      : {
          recurrence: 'once',
          title: input.title,
          kind: 'event',
          start_at: atKst(input.date, input.startHour),
          end_at: atKst(input.date, input.endHour),
        }
  return write(async () => {
    await request('/me/schedule/items', { method: 'POST', body }).catch((e: unknown) => {
      // 일정 추가 API가 아직 없으면(404·405) "잠시 후 다시" 대신 못 한다고 알린다.
      // 서버가 아직 매주 반복만 받아서(#58) 한 번만 일정은 422(days 빠짐)가 온다. "Field required" 대신 같은 안내
      if (e instanceof ApiError && (e.status === 404 || e.status === 405 || (input.recurrence === 'once' && e.status === 422))) {
        const what = input.recurrence === 'once' ? '일회성 일정은' : '일정을'
        throw new ApiError(e.status, 'SCHEDULE_ADD_UNAVAILABLE', `지금은 ${what} 직접 넣을 수 없어요.`)
      }
      throw e
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

type ServerIntegration = { imported_count: number; term?: string | null; term_state?: TermState | null }

/** 에브리타임 공유 링크로 수업 불러오기. 이미 연결돼 있으면 다시 불러온다 */
export function connectEverytime(url: string): Promise<LinkResult> {
  return write(async () => {
    // 서버가 에브리타임에 시간표를 한 번 요청해 읽는다(보통 2~4초, 서버 한도 15초). 한도보다 조금 길게 기다린다
    const r = await request<ServerIntegration>('/me/integrations/everytime', { method: 'POST', body: { url }, timeoutMs: 20_000 })
    return { count: r.imported_count, term: r.term ?? null, termState: r.term_state ?? null }
  })
}

const GOOGLE_CLIENT_ID = (import.meta.env.VITE_GOOGLE_CLIENT_ID ?? '').trim()
const CALENDAR_SCOPE = 'https://www.googleapis.com/auth/calendar.readonly' // 읽기 권한만
const GOOGLE_OFF = '지금은 구글 캘린더를 연결할 수 없어요. 시간표를 직접 넣어 주세요.'

/** 구글 권한 팝업을 열어 인증 코드를 받는다. 팝업을 닫으면 CANCELLED */
function askGoogleCode(): Promise<string> {
  const oauth2 = window.google?.accounts.oauth2 // index.html의 GSI 스크립트
  if (!GOOGLE_CLIENT_ID || !oauth2) return Promise.reject(new ApiError(503, 'GOOGLE_NOT_READY', GOOGLE_OFF))
  return new Promise((resolve, reject) => {
    oauth2
      .initCodeClient({
        client_id: GOOGLE_CLIENT_ID,
        scope: CALENDAR_SCOPE,
        ux_mode: 'popup',
        access_type: 'offline', // 서버가 나중에 다시 읽으려면 갱신 토큰이 있어야 한다
        prompt: 'consent', // 전에 허락했어도 갱신 토큰을 다시 받는다
        callback: (res) =>
          res.code ? resolve(res.code) : reject(new ApiError(400, 'GOOGLE_DENIED', '캘린더 읽기를 허락해야 연결돼요.')),
        error_callback: () => reject(new ApiError(400, 'CANCELLED', '구글 연결을 끝내지 않았어요.')),
      })
      .requestCode()
  })
}

/**
 * 구글 캘린더 연결. 팝업에서 받은 코드를 서버에 넘기면 서버가 앞으로 5주 약속을 "바쁨"으로 읽어 온다.
 * 팝업은 클릭 직후에 열어야 막히지 않으므로 버튼 클릭에서 바로 부른다(앞에 await를 두지 않는다).
 */
export function connectGoogle(): Promise<LinkResult> {
  const code = askGoogleCode()
  return write(async () => {
    const r = await request<ServerIntegration>('/me/integrations/google-calendar', {
      method: 'POST',
      body: { code: await code },
      timeoutMs: 25_000, // 토큰 교환 + 약속 읽기(구글 호출 각 10초 한도)
    })
    return { count: r.imported_count, term: null }
  })
}
