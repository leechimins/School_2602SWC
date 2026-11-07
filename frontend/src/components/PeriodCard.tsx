import { formatDDay, formatMD, periodOf } from '../lib/date.ts'
import type { IsoDate } from '../types/common.ts'
import styles from './PeriodCard.module.css'

type Props = {
  startDate: IsoDate
  dueDate: IsoDate
  today: IsoDate // 시연 시계 기준
}

// 기간 카드(홈·일정 맨 위): 왼쪽 마감 디데이 | 오른쪽 오늘 + 기간 막대(오늘 위치) + 시작·마감일.
// 단계도 점검일도 쓰지 않고 마감 디데이 하나로 본다.
export default function PeriodCard({ startDate, dueDate, today }: Props) {
  const { total, passed, left } = periodOf(startDate, dueDate, today)
  const at = Math.round((passed / total) * 100)
  return (
    <section className={`sec ${styles.hero}`}>
      <div>
        <span className={styles.label}>마감까지</span>
        <b className={`${styles.dday} num`}>{formatDDay(left)}</b>
      </div>
      <div className={styles.right}>
        <span className={`${styles.today} num`}>오늘 {formatMD(today)}</span>
        <div className={styles.period} role="img" aria-label={`전체 ${total}일 중 ${passed}일 지남`}>
          <i style={{ width: `${at}%` }} />
          <b style={{ left: `${at}%` }} />
        </div>
        <div className="row-between">
          <span className="meta num">{formatMD(startDate)} 시작</span>
          <span className="meta num">{formatMD(dueDate)} 마감</span>
        </div>
      </div>
    </section>
  )
}
