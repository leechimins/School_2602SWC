import type { NoticeKind } from '../types/notification.ts'
import type { Burden } from '../types/scheduling.ts'
import type { TaskStatus } from '../types/task.ts'

// 상태 → 뱃지 색. 색만으로 구분하지 않고 뱃지에는 늘 글자가 함께 붙는다.
// ok(초록)는 끝난·좋은 상태, here(보라)는 진행 중, warn·danger는 챙길 것. 담당자 없음은 정상 상태라 오류색을 쓰지 않는다.
export type Tone = 'plain' | 'ok' | 'warn' | 'danger' | 'here'

export const TASK_STATUS_TONE: Record<TaskStatus, Tone> = {
  '시작 전': 'plain',
  '진행 중': 'here',
  막힘: 'danger',
  완료: 'ok',
}

// 늦음·막힘은 챙기라는 알림, 완료는 좋은 소식
export const NOTICE_TONE: Record<NoticeKind, Tone> = {
  늦음: 'danger',
  막힘: 'warn',
  완료: 'ok',
  '회의 30분 전': 'ok',
  '회의 제안': 'warn',
  '회의 확정': 'ok',
}

export const BURDEN_TONE: Record<Burden, Tone> = {
  괜찮음: 'ok',
  조금: 'warn',
  많이: 'danger',
}

/** 남의 불편 정도를 뱃지 글자로: "수락 · 조금 불편" */
export const BURDEN_LABEL: Record<Burden, string> = {
  괜찮음: '괜찮음',
  조금: '조금 불편',
  많이: '많이 불편',
}
