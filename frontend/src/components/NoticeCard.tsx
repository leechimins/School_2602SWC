import { Link } from 'react-router-dom'
import { NOTICE_TONE } from '../lib/tones.ts'
import type { Notice } from '../types/notification.ts'
import Badge from './Badge.tsx'
import styles from './NoticeCard.module.css'

type Props = {
  notice: Notice
  /** 누르면 갈 곳: 할 일 알림은 할 일로, 회의 알림은 회의로. label은 화면 읽기용 이름 */
  action?: { label: string; to: string }
  /** 눌렀을 때(읽음 처리) */
  onOpen?: () => void
}

// 알림 카드: [종류 뱃지] 이유 한 줄 [›]. 카드 전체가 한 덩어리로 눌린다. 이유는 서버(목)가 만든 문장 그대로
export default function NoticeCard({ notice, action, onOpen }: Props) {
  const body = (
    <>
      <Badge tone={NOTICE_TONE[notice.kind]}>{notice.kind}</Badge>
      <p className={styles.reason}>{notice.reason}</p>
      {action && (
        <span className={styles.go} aria-hidden="true">
          ›
        </span>
      )}
    </>
  )
  return action ? (
    <Link to={action.to} className={styles.card} data-read={notice.read} aria-label={`${notice.kind}: ${notice.reason} — ${action.label}`} onClick={onOpen}>
      {body}
    </Link>
  ) : (
    <article className={styles.card} data-read={notice.read}>
      {body}
    </article>
  )
}
