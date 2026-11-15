import { Link } from 'react-router-dom'
import styles from './MoreLink.module.css'

type Props = {
  to: string
  label: string
}

// 다른 화면으로 넘어가는 한 줄 (알림·My의 "에이전트 기록"). 줄 전체가 눌린다
export default function MoreLink({ to, label }: Props) {
  return (
    <Link to={to} className={`sec ${styles.more}`}>
      <span className="strong">{label}</span>
      <span className={styles.chevron} aria-hidden="true">
        ›
      </span>
    </Link>
  )
}
