import type { MeetingBrief, MeetingDetail } from '../types/meeting.ts'

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

/**
 * 참석자 이름. 서버는 회의안에 수락한 사람만 참석자로 준다(minutes/record.py _attendees).
 * 조율 없이 바로 기록한 회의는 수락한 사람이 없으므로, 받아적은 원문에서 말한 사람을 참석자로 본다.
 */
export function attendeeNames(m: MeetingDetail): string[] {
  if (m.attendees.length > 0) return m.attendees
  return [...new Set(m.transcript.flatMap((line) => (line.speakerName ? [line.speakerName] : [])))]
}
