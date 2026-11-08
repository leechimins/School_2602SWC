import { dateParts } from '../lib/date.ts'
import type { IsoDateTime } from '../types/common.ts'
import styles from './DateBlock.module.css'

type Props = {
  at?: IsoDateTime // 없으면 아직 날짜가 안 정해진 회의(조율 중): "–"
  muted?: boolean // 지난 회의·조율 중은 회색
}

// 회의 날짜 칸(홈 다음 회의 · 일정 회의 목록 공통): 월 / 일 / 요일
export default function DateBlock({ at, muted = false }: Props) {
  const parts = at ? dateParts(at) : null
  return (
    <span className={`${styles.date} ${muted ? styles.muted : ''} num`}>
      {parts ? (
        <>
          <small>{parts.month}</small>
          <b>{parts.day}</b>
          <small>{parts.weekday}</small>
        </>
      ) : (
        <b>–</b>
      )}
    </span>
  )
}
