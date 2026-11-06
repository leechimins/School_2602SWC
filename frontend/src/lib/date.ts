import dayjs, { type Dayjs } from 'dayjs'
import type { IsoDate } from '../types/common.ts'

// 날짜·시각을 화면 글자로 바꾸는 곳은 이 파일 하나다. 화면마다 따로 만들면 표기가 갈린다.
// "지금"은 인자로 받는다(useClock·getNow). 여기서 인자 없는 dayjs()를 부르지 않는다.

type DateInput = string | Dayjs

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'] as const

const d = (value: DateInput) => dayjs(value)

/** 요일 한 글자: 수 */
export function weekday(value: DateInput) {
  return WEEKDAYS[d(value).day()]
}

/** 기한 표기: 11/20 */
export function formatMD(value: DateInput) {
  return d(value).format('M/D')
}

/** 11월 20일 */
export function formatMonthDay(value: DateInput) {
  return d(value).format('M월 D일')
}

/** 오늘 날짜처럼 짧게: 11월 10일 화 */
export function formatDayLabel(value: DateInput) {
  return `${formatMonthDay(value)} ${weekday(value)}`
}

/** 회의 날짜처럼 길게: 11월 18일 수요일 */
export function formatLongDate(value: DateInput) {
  return `${formatMonthDay(value)} ${weekday(value)}요일`
}

/** 16:00 */
export function formatTime(value: DateInput) {
  return d(value).format('HH:mm')
}

/** 16:00–18:00 */
export function formatTimeRange(start: DateInput, end: DateInput) {
  return `${formatTime(start)}–${formatTime(end)}`
}

/** 회의 시간 한 줄: 11/18(수) 16:00–18:00 */
export function formatSlot(start: DateInput, end: DateInput) {
  return `${formatMD(start)}(${weekday(start)}) ${formatTimeRange(start, end)}`
}

/** 조율 기간: 11/16–11/20 */
export function formatRange(start: DateInput, end: DateInput) {
  return `${formatMD(start)}–${formatMD(end)}`
}

/** 회의 길이: 40분 · 2시간 · 1시간 30분 */
export function formatDuration(minutes: number) {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  if (h === 0) return `${m}분`
  return m === 0 ? `${h}시간` : `${h}시간 ${m}분`
}

/** 시작~끝 사이의 분 */
export function minutesBetween(start: DateInput, end: DateInput) {
  return d(end).diff(d(start), 'minute')
}

/** 날짜 칸(YYYY-MM-DD) */
export function toIsoDate(value: DateInput): IsoDate {
  return d(value).format('YYYY-MM-DD')
}

/** 달력 날짜로 센 남은 날. 지났으면 음수 (마감 디데이, 늦은 날 수) */
export function daysUntil(target: DateInput, now: Dayjs) {
  return d(target).startOf('day').diff(now.startOf('day'), 'day')
}

/** 디데이 표기: D-31 · D-day · D+2 */
export function formatDDay(days: number) {
  if (days === 0) return 'D-day'
  return days > 0 ? `D-${days}` : `D+${-days}`
}

export type DueGroup = '기한 지남' | '오늘' | '내일' | '그 이후' | '기한 없음'

/** 내 할 일 묶음(홈). 완료 묶음은 상태로 따로 나눈다 */
export function dueGroup(due: IsoDate | null, now: Dayjs): DueGroup {
  if (!due) return '기한 없음'
  const days = daysUntil(due, now)
  if (days < 0) return '기한 지남'
  if (days === 0) return '오늘'
  if (days === 1) return '내일'
  return '그 이후'
}
