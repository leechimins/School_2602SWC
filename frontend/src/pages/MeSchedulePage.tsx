import { useState } from 'react'
import { getMyWeek } from '../api/me.ts'
import RetryBox from '../components/RetryBox.tsx'
import ScheduleForm from '../components/ScheduleForm.tsx'
import ScheduleLinks from '../components/ScheduleLinks.tsx'
import Screen from '../components/Screen.tsx'
import Segmented from '../components/Segmented.tsx'
import WeekGrid from '../components/WeekGrid.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useClock } from '../hooks/useClock.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { formatRange, toIsoDate } from '../lib/date.ts'
import { PATHS } from '../lib/paths.ts'
import styles from './MePage.module.css'

const WEEKS = ['이번 주', '다음 주'] as const

// 마이 > 시간표 연동: 내 일정 가져오기(에브리타임·구글 캘린더·직접 입력) + 내 시간(주간 시간표)
export default function MeSchedulePage() {
  const user = useCurrentUser()
  const now = useClock()
  const [week, setWeek] = useState<(typeof WEEKS)[number]>('이번 주')
  const [adding, setAdding] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const anyDay = toIsoDate(week === '이번 주' ? now : now.add(7, 'day'))
  const thisWeek = useApi(() => getMyWeek(user.roomId, toIsoDate(now)), [user.roomId, user.id, toIsoDate(now)])
  const shown = useApi(() => getMyWeek(user.roomId, anyDay), [user.roomId, user.id, anyDay])

  const openAdd = () => {
    setAdding(true)
    setNotice(null)
  }

  return (
    <Screen title="시간표 연동" backTo={PATHS.me}>
      <section className="sec">
        <h2 className={styles.cardTitle}>내 일정 가져오기</h2>
        {thisWeek.status === 'error' && <RetryBox message={thisWeek.message} onRetry={thisWeek.reload} />}
        {thisWeek.status === 'ready' && <ScheduleLinks blocks={thisWeek.data.blocks} onAddManual={openAdd} />}
      </section>

      <section className="sec">
        <div className="row-between">
          <h2 className={styles.cardTitle}>내 시간</h2>
          {shown.status === 'ready' && <span className="meta num">{formatRange(shown.data.weekStart, shown.data.weekEnd)}</span>}
        </div>
        <Segmented label="주" options={WEEKS} value={week} onChange={setWeek} />
        {shown.status === 'error' && <RetryBox message={shown.message} onRetry={shown.reload} />}
        {shown.status === 'ready' && <WeekGrid blocks={shown.data.blocks} />}
        {notice && (
          <p className={`meta ${styles.notice}`} role="status">
            {notice}
          </p>
        )}
        {adding ? (
          <ScheduleForm
            onCancel={() => setAdding(false)}
            onSaved={(message) => {
              setAdding(false)
              setNotice(message)
            }}
          />
        ) : (
          <button type="button" className="btn small block" onClick={openAdd}>
            + 일정 추가 (수업 · 알바 · 약속 같은 개인 일정)
          </button>
        )}
      </section>
    </Screen>
  )
}
