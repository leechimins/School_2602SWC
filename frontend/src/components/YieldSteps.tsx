import { YIELD_LEVELS, type YieldLevel } from '../types/room.ts'
import styles from './YieldSteps.module.css'

type Props = {
  level: YieldLevel
}

// 누적 양보 단계 막대(세 칸). 숫자 없이 단계로만 보이고, 옆에 늘 단계 이름 글자를 함께 둔다
const FILLED: Record<YieldLevel, number> = { '아직 없음': 0, '조금 맞춰 줌': 1, '많이 맞춰 줌': 3 }

export default function YieldSteps({ level }: Props) {
  return (
    <span className={styles.steps} aria-hidden="true">
      {YIELD_LEVELS.map((_, i) => (
        <i key={i} className={i < FILLED[level] ? styles.on : undefined} />
      ))}
    </span>
  )
}
