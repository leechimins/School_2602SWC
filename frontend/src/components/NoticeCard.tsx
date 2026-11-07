import { Link } from 'react-router-dom'
import { NOTICE_TONE } from '../lib/tones.ts'
import type { Notice } from '../types/notification.ts'
import Badge from './Badge.tsx'
import styles from './NoticeCard.module.css'

type Props = {
  notice: Notice
  /** 이동 버튼: 할 일 알림은 할 일로, 회의 알림은 회의로 */
  action?: { label: string; to: string }
  /** 이동 버튼을 누를 때(읽음 처리) */
  onOpen?: () => void
}

// 알림 카드: 종류 뱃지 → 이유 한 줄 → 이동 버튼. 이유는 서버(목)가 할 일 데이터로 만든 문장 그대로
export default function NoticeCard({ notice, action, onOpen }: Props) {
  return (
    <article className={styles.card} data-read={notice.read}>
      <div className={styles.head}>
        <Badge tone={NOTICE_TONE[notice.kind]}>{notice.kind}</Badge>
        {action && (
          <Link to={action.to} className={`link ${styles.go}`} onClick={onOpen}>
            {action.label}
          </Link>
        )}
      </div>
      <p className={styles.reason}>{notice.reason}</p>
    </article>
  )
}
