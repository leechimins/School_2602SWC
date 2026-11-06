import { getNotices } from '../api/notifications.ts'
import EmptyState from '../components/EmptyState.tsx'
import NoticeCard from '../components/NoticeCard.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { PATHS, pathTo } from '../lib/paths.ts'
import type { Notice } from '../types/notification.ts'

// 알림: 맨 위가 "먼저 챙길 것". 읽음 처리·에이전트 기록·양보 기록은 #26에서 채운다
export default function NotificationsPage() {
  const user = useCurrentUser()
  const res = useApi(() => getNotices(user.roomId), [user.roomId, user.id])

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
    </Screen>
  )
}
