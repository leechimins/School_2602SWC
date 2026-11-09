import { useState } from 'react'
import { messageOf } from '../api/client.ts'
import { getPreferences, savePreferences } from '../api/me.ts'
import AgentQuote from '../components/AgentQuote.tsx'
import PrefForm from '../components/PrefForm.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { PATHS } from '../lib/paths.ts'
import type { Preferences } from '../types/me.ts'
import form from './Form.module.css'
import styles from './MePage.module.css'

// 마이 > 내 조건 / 선호 설정: 내 에이전트가 할 말 + 조건 네 가지 고치기
export default function MePrefsPage() {
  const user = useCurrentUser()
  const prefs = useApi(getPreferences, [user.id])

  return (
    <Screen title="내 조건 / 선호 설정" backTo={PATHS.me}>
      {prefs.status === 'error' && <RetryBox message={prefs.message} onRetry={prefs.reload} />}
      {prefs.status === 'ready' && (
        <>
          <AgentQuote name={user.name} prefs={prefs.data} />
          <section className="sec">
            <PrefEditor key={JSON.stringify(prefs.data)} initial={prefs.data} />
          </section>
        </>
      )}
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
