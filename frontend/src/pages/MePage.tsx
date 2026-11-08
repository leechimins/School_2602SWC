import { useState } from 'react'
import { Link } from 'react-router-dom'
import { messageOf } from '../api/client.ts'
import { getMyWeek, getPreferences, savePreferences } from '../api/me.ts'
import { getRoom } from '../api/rooms.ts'
import AgentQuote from '../components/AgentQuote.tsx'
import Avatar from '../components/Avatar.tsx'
import Badge from '../components/Badge.tsx'
import PrefForm from '../components/PrefForm.tsx'
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
import type { Preferences } from '../types/me.ts'
import form from './Form.module.css'
import styles from './MePage.module.css'

const WEEKS = ['이번 주', '다음 주'] as const

// 나 탭: 내 에이전트가 할 말 · 내 일정 가져오기 · 내 시간(주간 시간표) · 내가 좋아하는 방식(조건 네 가지) · 팀
export default function MePage() {
  const user = useCurrentUser()
  const now = useClock()
  const [week, setWeek] = useState<(typeof WEEKS)[number]>('이번 주')
  const [adding, setAdding] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const anyDay = toIsoDate(week === '이번 주' ? now : now.add(7, 'day'))
  const room = useApi(() => getRoom(user.roomId), [user.roomId, user.id])
  const prefs = useApi(getPreferences, [user.id])
  const thisWeek = useApi(() => getMyWeek(user.roomId, toIsoDate(now)), [user.roomId, user.id, toIsoDate(now)])
  const shown = useApi(() => getMyWeek(user.roomId, anyDay), [user.roomId, user.id, anyDay])

  const openAdd = () => {
    setAdding(true)
    setNotice(null)
  }

  return (
    <Screen title="나">
      <div className={styles.profile}>
        <Avatar name={user.name} size="large" />
        <div>
          <b className={styles.name}>{user.name}</b> {user.isLeader && <Badge tone="here">팀장</Badge>}
          {room.status === 'ready' && <p className="meta">{room.data.name}</p>}
        </div>
      </div>

      {prefs.status === 'error' && <RetryBox message={prefs.message} onRetry={prefs.reload} />}
      {prefs.status === 'ready' && <AgentQuote name={user.name} prefs={prefs.data} />}

      <section className="sec">
        <h2>내 일정 가져오기</h2>
        {thisWeek.status === 'error' && <RetryBox message={thisWeek.message} onRetry={thisWeek.reload} />}
        {thisWeek.status === 'ready' && <ScheduleLinks blocks={thisWeek.data.blocks} onAddManual={openAdd} />}
      </section>

      <section className="sec">
        <div className="row-between">
          <h2>내 시간</h2>
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

      <section className="sec">
        <h2>내가 좋아하는 방식</h2>
        {prefs.status === 'ready' && <PrefEditor key={JSON.stringify(prefs.data)} initial={prefs.data} />}
      </section>

      <section className="sec">
        <p className="meta">팀원 목록과 양보 점수, 초대 코드는 팀 화면에서 봐요.</p>
        <Link to={PATHS.team} className="link">
          팀 보기
        </Link>
      </section>
    </Screen>
  )
}

// 조건 고치기. 바꾸면 저장 버튼이 생기고, 저장하면 다음 조율부터 이 조건으로 말한다
function PrefEditor({ initial }: { initial: Preferences }) {
  const [draft, setDraft] = useState(initial)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const changed = JSON.stringify(draft) !== JSON.stringify(initial)

  const save = async () => {
    if (draft.fromHour !== null && draft.toHour !== null && draft.fromHour >= draft.toHour) {
      return setError('끝나는 시각이 시작보다 늦어야 해요.')
    }
    setSaving(true)
    setError(null)
    try {
      await savePreferences(draft, 'me') // 저장되면 새 값으로 다시 불러와 이 칸이 새로 그려진다
    } catch (e) {
      setError(messageOf(e))
      setSaving(false)
    }
  }

  return (
    <>
      <PrefForm value={draft} onChange={setDraft} />
      {error && (
        <p className={form.error} role="alert">
          {error}
        </p>
      )}
      {changed && (
        <div className={styles.act}>
          <button type="button" className="btn small quiet" onClick={() => setDraft(initial)}>
            취소
          </button>
          <button type="button" className="btn small primary" disabled={saving} onClick={save}>
            {saving ? '저장하는 중…' : '저장'}
          </button>
        </div>
      )}
    </>
  )
}
