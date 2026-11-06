import styles from './Badge.module.css'

type Props = {
  label?: string
}

// AI가 만든 것이 아직 확정 전임을 알리는 표시. 로봇·반짝이 아이콘 대신 글자로 보인다.
// 할 일 제안 카드, 판단 에이전트 말에 붙고, 사람이 확정하면 사라진다.
export default function AiMark({ label = 'AI 제안' }: Props) {
  return <span className={`${styles.badge} ${styles.ai}`}>{label}</span>
}
