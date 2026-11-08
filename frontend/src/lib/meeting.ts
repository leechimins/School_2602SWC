import type { MeetingBrief } from '../types/meeting.ts'

/**
 * 잡힌 회의의 응답 현황 한 줄 (홈 다음 회의 · 일정 잡힌 회의 공통)
 * 확정: "모두 수락했어요" / 확정 대기: "응답 1/4 · 내 응답 수락"
 * total(팀원 수)을 아직 모르면 응답 수는 빼고 내 응답만 보인다.
 */
export function answerLine(m: MeetingBrief, total: number | null) {
  // 조율 없이 "지금 회의 기록하기"로 만든 회의는 응답할 사람이 없다(내 응답도 없음)
  if (m.status === 'confirmed' && m.myState === null && !m.settled) return '바로 기록한 회의'
  if (m.status === 'confirmed') return '모두 수락했어요'
  const parts = [
    total ? `응답 ${total - m.pendingCount}/${total}` : null,
    m.myState ? `내 응답 ${m.myState}` : null,
  ]
  return parts.filter(Boolean).join(' · ')
}
