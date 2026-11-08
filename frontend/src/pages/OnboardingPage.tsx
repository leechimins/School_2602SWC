import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { messageOf } from '../api/client.ts'
import { getMyWeek, getPreferences, savePreferences } from '../api/me.ts'
import AgentQuote from '../components/AgentQuote.tsx'
import PrefForm from '../components/PrefForm.tsx'
import RetryBox from '../components/RetryBox.tsx'
import ScheduleForm from '../components/ScheduleForm.tsx'
import ScheduleLinks from '../components/ScheduleLinks.tsx'
import Screen from '../components/Screen.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useClock } from '../hooks/useClock.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { toIsoDate } from '../lib/date.ts'
import { PATHS } from '../lib/paths.ts'
import type { Preferences } from '../types/me.ts'
import form from './Form.module.css'
import styles from './OnboardingPage.module.css'

const TITLE = '내 조건 알려 주기'

// 온보딩(방에 처음 들어온 뒤 한 번): 조건 네 가지 → 내 일정 연결 → 내 에이전트 준비 완료.
// 필수는 없다. 네 칸을 다 비워도, 일정을 연결하지 않아도 다음으로 넘어간다.
export default function OnboardingPage() {
  const prefs = useApi(getPreferences, [])
  const [step, setStep] = useState(0)

  if (prefs.status !== 'ready') {
    return <Screen title={TITLE}>{prefs.status === 'error' && <RetryBox message={prefs.message} onRetry={prefs.reload} />}</Screen>
  }
  if (step === 0) return <PrefStep initial={prefs.data} onNext={() => setStep(1)} />
  if (step === 1) return <LinkStep onPrev={() => setStep(0)} onNext={() => setStep(2)} />
  return <ReadyStep prefs={prefs.data} onPrev={() => setStep(1)} />
}

function Question({ title, hint }: { title: string; hint: string }) {
  return (
    <>
      <p className={styles.q}>{title}</p>
      <p className={`meta ${styles.hint}`}>{hint}</p>
    </>
  )
}

// 1단계: 조건 네 가지. "다음"을 누르면 저장한다(피하고 싶은 시간을 에이전트가 다듬느라 조금 걸릴 수 있다)
function PrefStep({ initial, onNext }: { initial: Preferences; onNext: () => void }) {
  const [draft, setDraft] = useState(initial)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const next = async () => {
    if (draft.fromHour !== null && draft.toHour !== null && draft.fromHour >= draft.toHour) {
      return setError('끝나는 시각이 시작보다 늦어야 해요.')
    }
    setSaving(true)
    try {
      await savePreferences(draft, 'onboarding')
      onNext()
    } catch (e) {
      setError(messageOf(e))
      setSaving(false)
    }
  }

  return (
    <Screen
      title={TITLE}
      dock={
        <div className="btn-row">
          <button type="button" className="btn primary" disabled={saving} onClick={next}>
            {saving ? '저장하는 중…' : '다음'}
          </button>
        </div>
      }
    >
      <Question title="회의 잡을 때 쓸 조건 네 가지" hint="고르지 않은 건 비워 둬도 돼요. 시작한 뒤에도 나 탭에서 언제든 고칠 수 있어요." />
      <section className="sec">
        <PrefForm value={draft} onChange={setDraft} />
        {error && (
          <p className={form.error} role="alert">
            {error}
          </p>
        )}
      </section>
    </Screen>
  )
}

// 2단계: 에브리타임 · 구글 캘린더 · 직접 입력. 하나도 안 했으면 버튼이 "나중에 하기"
function LinkStep({ onPrev, onNext }: { onPrev: () => void; onNext: () => void }) {
  const user = useCurrentUser()
  const today = toIsoDate(useClock())
  const week = useApi(() => getMyWeek(user.roomId, today), [user.roomId, user.id, today])
  const [adding, setAdding] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const linked = week.status === 'ready' && week.data.blocks.some((b) => b.source !== null)

  return (
    <Screen
      title={TITLE}
      dock={
        <div className="btn-row">
          <button type="button" className="btn quiet" onClick={onPrev}>
            이전
          </button>
          <button type="button" className={`btn ${linked ? 'primary' : ''}`} onClick={onNext}>
            {linked ? '다음' : '나중에 하기'}
          </button>
        </div>
      }
    >
      <Question title="내 일정 연결하기" hint="수업과 개인 일정 시간은 에이전트가 빼고 조율해요." />
      <section className="sec">
        {week.status === 'error' && <RetryBox message={week.message} onRetry={week.reload} />}
        {week.status === 'ready' && (
          <ScheduleLinks
            blocks={week.data.blocks}
            onAddManual={() => {
              setAdding(true)
              setNotice(null)
            }}
          />
        )}
        {notice && (
          <p className={`meta ${styles.notice}`} role="status">
            {notice}
          </p>
        )}
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
    </Screen>
  )
}

// 3단계: 고른 조건으로 에이전트가 할 말을 보여 주고 홈으로
function ReadyStep({ prefs, onPrev }: { prefs: Preferences; onPrev: () => void }) {
  const user = useCurrentUser()
  const navigate = useNavigate()
  return (
    <Screen
      title={TITLE}
      dock={
        <div className="btn-row">
          <button type="button" className="btn quiet" onClick={onPrev}>
            이전
          </button>
          <button type="button" className="btn primary" onClick={() => navigate(PATHS.home)}>
            시작하기
          </button>
        </div>
      }
    >
      <Question title="내 에이전트가 준비됐어요" hint="고른 조건으로 이렇게 말해요. 시작한 뒤에도 나 탭에서 언제든 고칠 수 있어요." />
      <AgentQuote name={user.name} prefs={prefs} />
    </Screen>
  )
}
