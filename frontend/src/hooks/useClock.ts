import dayjs, { type Dayjs } from 'dayjs'

// 앱에서 "지금"을 아는 곳. 컴포넌트는 useClock()을 쓰고 new Date()·Date.now()를 직접 부르지 않는다.
export function useClock(): Dayjs {
  return dayjs()
}
