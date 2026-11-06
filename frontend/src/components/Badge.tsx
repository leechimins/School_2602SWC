import type { ReactNode } from 'react'
import type { Tone } from '../lib/tones.ts'
import styles from './Badge.module.css'

type Props = {
  tone?: Tone
  children: ReactNode // 글자는 항상 있다. 색만 있는 점·테두리로 상태를 나타내지 않는다
}

// 상태 뱃지: 할 일 상태, 알림 종류, 불편 정도, 회의 상태
export default function Badge({ tone = 'plain', children }: Props) {
  return <span className={`${styles.badge} ${styles[tone]}`}>{children}</span>
}
