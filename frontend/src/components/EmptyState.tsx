import { Link } from 'react-router-dom'
import styles from './EmptyState.module.css'

type Props = {
  title: string // 좋은 상태면 좋다고 쓴다: "늦거나 막힌 일이 없어요"
  description?: string
  /** 다음 행동. 빈 화면에는 늘 다음 행동 버튼을 둔다(알림이 없을 때만 예외) */
  action?: { label: string; to: string } | { label: string; onClick: () => void }
}

// 빈 화면: 아무것도 없다는 말만 두지 않고 다음에 할 일을 함께 보여 준다. 왼쪽에 솜솜이를 작게 둔다(마스코트를 쓰는 두 곳 중 하나)
export default function EmptyState({ title, description, action }: Props) {
  return (
    <div className={styles.empty}>
      <img className={styles.art} src="/brand/somsom.webp" alt="" />
      <div>
        <p className="strong">{title}</p>
        {description && <p className="meta">{description}</p>}
        {action &&
          ('to' in action ? (
            <Link to={action.to} className={`link ${styles.action}`}>
              {action.label}
            </Link>
          ) : (
            <button type="button" className={`link ${styles.action}`} onClick={action.onClick}>
              {action.label}
            </button>
          ))}
      </div>
    </div>
  )
}
