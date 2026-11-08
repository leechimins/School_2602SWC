import type { IsoDate } from './common.ts'

// 내 조건(나 탭·온보딩): 회의 잡을 때 쓸 조건 네 가지와 내 주간 시간표.
// 서버 모양(분·오전오후·영문 enum)은 api/convert.ts가 이 모양으로 바꾼다.

export const WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일'] as const // 시간표 순서(0=월)

export const DAYPARTS = ['아침', '오전', '점심', '오후', '저녁', '밤'] as const
export type Daypart = (typeof DAYPARTS)[number]

export const PREF_MODES = ['대면', '비대면', '상관없음'] as const
export type PrefMode = (typeof PREF_MODES)[number]

/** 조건 네 가지. 필수는 없다 — 비어 있으면 조율이 그 조건을 안 쓴다 */
export type Preferences = {
  fromHour: number | null // 몇 시부터 (0~23)
  toHour: number | null // 몇 시까지
  mode: PrefMode | null
  dayparts: Daypart[]
  avoid: string // 꼭 피하고 싶은 시간. 사람이 쓴 한 줄 그대로(에이전트가 다듬어서 조율 근거로 쓴다)
}

/** 시간표 한 칸의 종류. 알바·약속은 "일정" 하나로 묶는다 */
export type WeekBlockKind = 'class' | 'event' | 'meeting' | 'waiting'
export type ScheduleSource = 'everytime' | 'google' | 'manual'

export type WeekBlock = {
  kind: WeekBlockKind
  title: string // 제목 없는 구글 약속은 '일정'
  weekday: number // 0=월 … 6=일
  startHour: number // 18.5 = 18:30
  endHour: number
  source: ScheduleSource | null // 팀 회의는 null
}

export type MyWeek = {
  weekStart: IsoDate // 그 주 월요일
  weekEnd: IsoDate
  blocks: WeekBlock[]
}

/** 일정 직접 추가(매주 반복): 이름 · 종류 · 요일마다 시간 */
export type ScheduleItemInput = {
  title: string
  kind: 'class' | 'event'
  days: { weekday: number; startHour: number; endHour: number }[]
}

/** 일정 연결 결과 한 줄: "수업 4개를 가져왔어요" */
export type LinkResult = { count: number }
