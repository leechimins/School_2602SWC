import type { Id } from '../types/common.ts'

// 화면 주소를 한 곳에 모은다. 화면 코드에서 '/schedule/...' 같은 문자열을 직접 쓰지 않고 이 표를 쓴다.
// 탭 구조는 디자인 브리프 "탭 구조"를 따른다: 회의 잡기(조율)와 알림은 홈 아래, 회의 기록·회의록은 일정 아래.
export const PATHS = {
  // 홈 탭
  home: '/',
  notifications: '/notifications',
  schedulingNew: '/scheduling/new',
  scheduling: '/scheduling/:schedulingId',
  proposal: '/proposals/:proposalId',
  // 일정 탭
  schedule: '/schedule',
  meeting: '/schedule/meetings/:meetingId',
  record: '/schedule/meetings/:meetingId/record',
  // 할 일 탭
  tasks: '/tasks',
  myTasks: '/tasks/mine',
  // 나 탭
  me: '/me',
  team: '/me/team',
  // 탭 밖 (처음 한 번)
  login: '/login', // 스플래시 + 구글 로그인
  start: '/start',
  onboarding: '/onboarding',
  // 시연 화면
  demo: '/demo',
} as const

export const pathTo = {
  scheduling: (id: Id) => `/scheduling/${id}`,
  proposal: (id: Id) => `/proposals/${id}`,
  meeting: (id: Id) => `/schedule/meetings/${id}`,
  record: (id: Id) => `/schedule/meetings/${id}/record`,
}

export type TabKey = 'home' | 'schedule' | 'tasks' | 'me'

/** 주소가 어느 탭 아래인지. 탭 아래 화면에서도 그 탭이 켜져 보인다 */
export function tabOf(pathname: string): TabKey {
  if (pathname.startsWith(PATHS.schedule)) return 'schedule'
  if (pathname.startsWith(PATHS.tasks)) return 'tasks'
  if (pathname.startsWith(PATHS.me)) return 'me'
  return 'home'
}
