import { useState } from 'react'
import { getActivity, getNotices, markNoticesRead } from '../api/notifications.ts'
import EmptyState from '../components/EmptyState.tsx'
import NoticeCard from '../components/NoticeCard.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { formatStamp } from '../lib/date.ts'
import { withJosa } from '../lib/korean.ts'
import { PATHS, pathTo } from '../lib/paths.ts'
import type { Notice } from '../types/notification.ts'
import styles from './NotificationsPage.module.css'

// 알림(홈 오른쪽 위 종): 먼저 챙길 것(늦음 → 막힘 → 완료 → 회의) → 에이전트 기록(무엇을·왜) → 양보 기록.
// 이동 버튼을 누르거나 "모두 읽음"을 누르면 읽음으로 바뀌고 홈 종의 숫자가 줄어든다.
export default function NotificationsPage() {
  const user = useCurrentUser()
  const res = useApi(() => getNotices(user.roomId), [user.roomId, user.id])
  const activity = useApi(() => getActivity(user.roomId), [user.roomId, user.id])

  const read = (ids: string[]) => ids.length > 0 && markNoticesRead(user.roomId, ids)
  const unread = res.status === 'ready' ? res.data.notices.filter((n) => !n.read).map((n) => n.id) : []

  const actionOf = (n: Notice) => {
    if (n.taskId) return { label: '할 일 보기', to: PATHS.tasks }
    if (n.meetingId) return { label: '회의 보기', to: pathTo.proposal(n.meetingId) }
    return undefined
  }

  const readAll = unread.length > 0 && (
    <button type="button" className={`link ${styles.aux}`} onClick={() => read(unread)}>
      모두 읽음
    </button>
  )

  return (
    <Screen title="알림" backTo={PATHS.home} aux={readAll}>
      <PushPermission />
      {res.status === 'error' && <RetryBox message={res.message} onRetry={res.reload} />}
      {res.status === 'ready' && (
        <section className="sec">
          <h2>먼저 챙길 것</h2>
          {res.data.notices.length === 0 ? (
            <EmptyState title="늦거나 막힌 일이 없어요" description="팀이 잘 가고 있어요. 챙길 일이 생기면 여기에 알려 드려요." />
          ) : (
            res.data.notices.map((n) => (
              <NoticeCard key={n.id} notice={n} action={actionOf(n)} onOpen={() => !n.read && read([n.id])} />
            ))
          )}
        </section>
      )}
      {activity.status === 'ready' && (
        <>
          <section className="sec">
            <h2>에이전트 기록</h2>
            {activity.data.agentLog.length === 0 ? (
              <p className="meta">아직 에이전트가 한 일이 없어요. 회의를 잡거나 기록하면 무엇을 왜 했는지 여기에 남겨요.</p>
            ) : (
              activity.data.agentLog.map((a) => (
                <div key={a.id} className={`${styles.record} ${styles.log}`}>
                  <p className="strong">{a.what}</p>
                  <span className="meta num">{formatStamp(a.at)}</span>
                </div>
              ))
            )}
          </section>
          <section className="sec">
            <h2>양보 기록</h2>
            {activity.data.yieldRecords.length === 0 ? (
              <p className="meta">회의가 잡히면 누가 맞춰 줬는지 남겨요.</p>
            ) : (
              activity.data.yieldRecords.map((y) => (
                <div key={y.id} className={styles.record}>
                  <p className={styles.yieldHead}>
                    <span className="strong">{y.meetingLabel}</span>
                    <span>{withJosa(y.name, '이/가')} 맞춰 줬어요</span>
                  </p>
                  <p className="meta">{y.why}</p>
                </div>
              ))
            )}
          </section>
        </>
      )}
    </Screen>
  )
}

type Permission = NotificationPermission | 'unsupported'

const permissionNow = (): Permission => (typeof Notification === 'undefined' ? 'unsupported' : Notification.permission)

// 웹 푸시 권한: 아직 안 물었으면 켜기 버튼, 거부했으면 앱 안에서만 알린다고 쓴다. 허락했으면 아무것도 그리지 않는다
function PushPermission() {
  const [permission, setPermission] = useState<Permission>(permissionNow)
  if (permission === 'granted') return null

  if (permission === 'default') {
    return (
      <section className={`sec ${styles.push}`}>
        <p className="meta">휴대폰 알림을 켜면 늦음·막힘과 회의 30분 전을 바로 알려 드려요.</p>
        <button
          type="button"
          className="btn small"
          onClick={() => Notification.requestPermission().then(setPermission, () => setPermission('denied'))}
        >
          알림 켜기
        </button>
      </section>
    )
  }
  return (
    <section className={`sec ${styles.push}`}>
      <p className="meta">휴대폰 알림이 꺼져 있어요. 앱 안에서만 알려 드려요.</p>
    </section>
  )
}
