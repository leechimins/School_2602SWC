import { getActivity, getNotices } from '../api/notifications.ts'
import EmptyState from '../components/EmptyState.tsx'
import NoticeCard from '../components/NoticeCard.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { withJosa } from '../lib/korean.ts'
import { PATHS, pathTo } from '../lib/paths.ts'
import type { Notice } from '../types/notification.ts'
import styles from './NotificationsPage.module.css'

// 알림: 맨 위가 "먼저 챙길 것", 아래에 양보 기록(회의마다 누가 왜 맞춰 줬는지). 읽음 처리·에이전트 기록은 #26에서 채운다
export default function NotificationsPage() {
  const user = useCurrentUser()
  const res = useApi(() => getNotices(user.roomId), [user.roomId, user.id])
  const activity = useApi(() => getActivity(user.roomId), [user.roomId])

  const actionOf = (n: Notice) =>
    n.taskId ? { label: '할 일 보기', to: PATHS.tasks } : n.meetingId ? { label: '회의 보기', to: pathTo.proposal(n.meetingId) } : undefined

  return (
    <Screen title="알림" backTo={PATHS.home}>
      {res.status === 'error' && <RetryBox message={res.message} onRetry={res.reload} />}
      {res.status === 'ready' && (
        <section className="sec">
          <h2>먼저 챙길 것</h2>
          {res.data.notices.length === 0 ? (
            <EmptyState title="늦거나 막힌 일이 없어요" description="팀이 잘 가고 있어요. 챙길 일이 생기면 여기에 알려 드려요." />
          ) : (
            res.data.notices.map((n) => <NoticeCard key={n.id} notice={n} action={actionOf(n)} />)
          )}
        </section>
      )}
      {activity.status === 'ready' && (
        <section className="sec">
          <h2>양보 기록</h2>
          {activity.data.yieldRecords.length === 0 ? (
            <p className="meta">아직 잡은 회의가 없어요. 회의가 잡히면 누가 맞춰 줬는지 여기에 남겨요.</p>
          ) : (
            activity.data.yieldRecords.map((y) => (
              <div key={y.id} className={styles.record}>
                <p className="strong">{y.meetingLabel}</p>
                <p>{withJosa(y.name, '이/가')} 맞춰 줬어요</p>
                <p className="meta">{y.why}</p>
              </div>
            ))
          )}
        </section>
      )}
    </Screen>
  )
}
