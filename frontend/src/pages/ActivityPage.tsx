import { useLocation, useSearchParams } from 'react-router-dom'
import { getActivity } from '../api/notifications.ts'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import Segmented from '../components/Segmented.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { formatStamp } from '../lib/date.ts'
import { withJosa } from '../lib/korean.ts'
import { PATHS } from '../lib/paths.ts'
import styles from './ActivityPage.module.css'

const TABS = ['한 일', '양보'] as const
type Tab = (typeof TABS)[number]

// 에이전트 기록: 에이전트가 무엇을 왜 했는지(한 일)와 누가 시간을 맞춰 줬는지(양보).
// 알림 화면 아래(/notifications/activity)와 My 탭 팀원 묶음의 "양보 기록 보기"(/me/activity?tab=yield)에서 들어온다. 주소가 둘이라 들어온 탭이 그대로 켜진다.
// 알림은 "먼저 챙길 것"만 두고, 쌓이는 기록은 여기서 본다.
export default function ActivityPage() {
  const user = useCurrentUser()
  const res = useApi(() => getActivity(user.roomId), [user.roomId, user.id])
  // 탭은 주소(?tab=yield)에 둔다. My의 "양보 기록 보기"가 양보 탭으로 바로 연다
  const [params, setParams] = useSearchParams()
  const tab: Tab = params.get('tab') === 'yield' ? '양보' : '한 일'
  const setTab = (t: Tab) => setParams(t === '양보' ? { tab: 'yield' } : {}, { replace: true })
  const fromMe = useLocation().pathname.startsWith(PATHS.me)

  return (
    <Screen title="에이전트 기록" backTo={fromMe ? PATHS.me : PATHS.notifications}>
      <div className={styles.tabs}>
        <Segmented label="기록 종류" options={TABS} value={tab} onChange={setTab} />
      </div>
      {res.status === 'error' && <RetryBox message={res.message} onRetry={res.reload} />}
      {res.status === 'ready' && tab === '한 일' && (
        <section className="sec">
          {res.data.agentLog.length === 0 ? (
            <p className="meta">아직 에이전트가 한 일이 없어요.</p>
          ) : (
            res.data.agentLog.map((a) => (
              <div key={a.id} className={`${styles.record} ${styles.log}`}>
                <p className="strong">{a.what}</p>
                <span className="meta num">{formatStamp(a.at)}</span>
              </div>
            ))
          )}
        </section>
      )}
      {res.status === 'ready' && tab === '양보' && (
        <section className="sec">
          {res.data.yieldRecords.length === 0 ? (
            <p className="meta">회의가 잡히면 누가 맞춰 줬는지 남겨요.</p>
          ) : (
            res.data.yieldRecords.map((y) => (
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
      )}
    </Screen>
  )
}
