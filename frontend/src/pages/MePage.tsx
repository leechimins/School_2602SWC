import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { isRealServer, messageOf } from '../api/client.ts'
import { getMyWeek, getPreferences, savePreferences } from '../api/me.ts'
import { getRoom } from '../api/rooms.ts'
import { signOut } from '../api/session.ts'
import AgentQuote from '../components/AgentQuote.tsx'
import Avatar from '../components/Avatar.tsx'
import Badge from '../components/Badge.tsx'
import PrefForm from '../components/PrefForm.tsx'
import RetryBox from '../components/RetryBox.tsx'
import ScheduleEditSheet from '../components/ScheduleEditSheet.tsx'
import ScheduleForm from '../components/ScheduleForm.tsx'
import ScheduleLinks from '../components/ScheduleLinks.tsx'
import Screen from '../components/Screen.tsx'
import Segmented from '../components/Segmented.tsx'
import Sheet from '../components/Sheet.tsx'
import TeamSection from '../components/TeamSection.tsx'
import WeekGrid from '../components/WeekGrid.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useClock } from '../hooks/useClock.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { formatRange, toIsoDate } from '../lib/date.ts'
import { PATHS } from '../lib/paths.ts'
import type { Preferences, WeekBlock } from '../types/me.ts'
import form from './Form.module.css'
import styles from './MePage.module.css'

const WEEKS = ['이번 주', '다음 주'] as const

// My 탭: 내 에이전트가 할 말(+ 좋아하는 방식 바꾸기 시트) · 내 일정 가져오기 · 내 시간(주간 시간표) · 팀 · 로그아웃
export default function MePage() {
  const user = useCurrentUser()
  const now = useClock()
  const navigate = useNavigate()
  const [week, setWeek] = useState<(typeof WEEKS)[number]>('이번 주')
  const [adding, setAdding] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [editingPrefs, setEditingPrefs] = useState(false)
  const [editingBlock, setEditingBlock] = useState<WeekBlock | null>(null)

  const anyDay = toIsoDate(week === '이번 주' ? now : now.add(7, 'day'))
  const room = useApi(() => getRoom(user.roomId), [user.roomId, user.id])
  const prefs = useApi(getPreferences, [user.id])
  const thisWeek = useApi(() => getMyWeek(user.roomId, toIsoDate(now)), [user.roomId, user.id, toIsoDate(now)])
  const shown = useApi(() => getMyWeek(user.roomId, anyDay), [user.roomId, user.id, anyDay])

  const openAdd = () => {
    setAdding(true)
    setNotice(null)
  }

  const logout = async () => {
    await signOut()
    navigate(PATHS.login, { replace: true })
  }

  return (
    <Screen title="My">
      <div className={styles.profile}>
        <Avatar name={user.name} size="large" />
        <div>
          <b className={styles.name}>{user.name}</b> {user.isLeader && <Badge tone="here">팀장</Badge>}
          {room.status === 'ready' && <p className="meta">{room.data.name}</p>}
        </div>
        {prefs.status === 'ready' && (
          <button type="button" className={`btn small ${styles.prefBtn}`} onClick={() => setEditingPrefs(true)}>
            좋아하는 방식 바꾸기
          </button>
        )}
      </div>

      {prefs.status === 'error' && <RetryBox message={prefs.message} onRetry={prefs.reload} />}
      {prefs.status === 'ready' && (
        <>
          <AgentQuote name={user.name} prefs={prefs.data} />
          {editingPrefs && <PrefSheet initial={prefs.data} onClose={() => setEditingPrefs(false)} />}
        </>
      )}

      <section className="sec">
        <div className={styles.secHead}>
          <h2>내 일정 가져오기</h2>
          <span>팀원에겐 바쁜지만 보여요</span>
        </div>
        {thisWeek.status === 'error' && <RetryBox message={thisWeek.message} onRetry={thisWeek.reload} />}
        {thisWeek.status === 'ready' && <ScheduleLinks blocks={thisWeek.data.blocks} showLock={false} />}
      </section>

      <section className="sec">
        <div className="row-between">
          <div className={styles.secHead}>
            <h2>내 시간</h2>
            <span>직접 넣은 일정은 길게 눌러 수정</span>
          </div>
          {shown.status === 'ready' && <span className="meta num">{formatRange(shown.data.weekStart, shown.data.weekEnd)}</span>}
        </div>
        <Segmented label="주" options={WEEKS} value={week} onChange={setWeek} />
        {shown.status === 'error' && <RetryBox message={shown.message} onRetry={shown.reload} />}
        {shown.status === 'ready' && <WeekGrid blocks={shown.data.blocks} onEdit={setEditingBlock} />}
        {editingBlock && <ScheduleEditSheet block={editingBlock} onClose={() => setEditingBlock(null)} />}
        {notice && (
          <p className={`meta ${styles.notice}`} role="status">
            {notice}
          </p>
        )}
        <button type="button" className="btn small block" onClick={openAdd}>
          + 일정 추가 (수업 · 알바 · 약속 같은 개인 일정)
        </button>
        {adding && (
          <ScheduleForm
            onCancel={() => setAdding(false)}
            onSaved={(message) => {
              setAdding(false)
              setNotice(message)
            }}
          />
        )}
      </section>

      {room.status === 'error' && <RetryBox message={room.message} onRetry={room.reload} />}
      {room.status === 'ready' && <TeamSection room={room.data} />}
      {/* 목 모드에는 로그인이 없어서 숨긴다 */}
      {isRealServer() && (
        <button type="button" className="btn quiet block" onClick={logout}>
          로그아웃
        </button>
      )}
    </Screen>
  )
}

// 좋아하는 방식(조건 네 가지) 고치기 시트. 저장하면 다음 조율부터 이 조건으로 말한다
function PrefSheet({ initial, onClose }: { initial: Preferences; onClose: () => void }) {
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
      await savePreferences(draft, 'me') // 저장되면 새 값으로 다시 불러와 위 에이전트 말이 바뀐다
      onClose()
    } catch (e) {
      setError(messageOf(e))
      setSaving(false)
    }
  }

  return (
    <Sheet
      title="내가 좋아하는 방식"
      onClose={onClose}
      actions={
        <>
          <button type="button" className="btn quiet" onClick={onClose}>
            취소
          </button>
          <button type="button" className="btn primary" disabled={!changed || saving} onClick={save}>
            {saving ? '저장하는 중…' : '저장'}
          </button>
        </>
      }
    >
      <PrefForm value={draft} onChange={setDraft} />
      {error && (
        <p className={form.error} role="alert">
          {error}
        </p>
      )}
    </Sheet>
  )
}
