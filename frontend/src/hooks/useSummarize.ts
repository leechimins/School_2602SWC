import { useState } from 'react'
import { summarizeMeeting } from '../api/records.ts'
import type { Id } from '../types/common.ts'

export type SummarizePhase = 'idle' | 'working' | 'failed'

/**
 * 회의록 정리(AI) 한 번의 상태: 정리 중 → 끝 / 실패.
 * 실패해도 원문은 이미 저장돼 있어 "다시 하기"는 같은 원문으로 다시 정리한다.
 * 회의 기록 화면(받아적기·직접 쓰기 직후)과 회의록 화면(정리 전 원문)이 같이 쓴다.
 */
export function useSummarize(roomId: Id, meetingId: Id) {
  const [phase, setPhase] = useState<SummarizePhase>('idle')

  const run = async (): Promise<boolean> => {
    setPhase('working')
    try {
      await summarizeMeeting(roomId, meetingId)
      setPhase('idle')
      return true
    } catch {
      setPhase('failed')
      return false
    }
  }

  return { phase, run }
}
