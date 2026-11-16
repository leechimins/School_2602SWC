import { useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
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
import { showNotice } from '../lib/notice.ts'
import { PATHS } from '../lib/paths.ts'
import type { Preferences, Recurrence } from '../types/me.ts'
import form from './Form.module.css'
import styles from './OnboardingPage.module.css'

const TITLE = '내 조건 알려 주기'

// 온보딩(방에 처음 들어온 뒤 한 번): 조건 네 가지 → 내 일정 연결 → 내 에이전트 준비 완료.
// 필수는 없다. 네 칸을 다 비워도, 일정을 연결하지 않아도 다음으로 넘어간다.
// 단계는 주소(?step=1)에 남겨 브라우저 뒤로 가기·제목줄 뒤로·"이전"이 모두 한 단계씩 돌아간다.
// 첫 단계에는 제목줄 뒤로 버튼이 없다: 방은 이미 만들었거나 들어와서 돌아갈 화면이 없고,
// 뒤로가 말없이 홈으로 가면 온보딩을 건너뛴 줄 모른다. 건너뛰기는 "나중에 하기"로만 한다(조건은 My 탭에서 언제든 고친다).
export default function OnboardingPage() {
  const prefs = useApi(getPreferences, [])
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const step = Math.min(Math.max(Number(params.get('step')) || 0, 0), 2)

  const next = () => setParams({ step: String(step + 1) }, { state: { stepped: true } })
  const skip = () => navigate(PATHS.home)
  const prev = () => {
    // "다음"으로 온 단계면 기록을 하나 되돌리고, 주소로 바로 연 단계면 앞 단계로 바꿔 끼운다
    if ((location.state as { stepped?: boolean } | null)?.stepped) return navigate(-1)
    setParams(step === 1 ? {} : { step: String(step - 1) }, { replace: true })
  }

  if (prefs.status !== 'ready') {
    return (
      <Screen title={TITLE} onBack={step > 0 ? prev : undefined}>
        {prefs.status === 'error' && <RetryBox message={prefs.message} onRetry={prefs.reload} />}
      </Screen>
    )
  }
  if (step === 0) return <PrefStep initial={prefs.data} onSkip={skip} onNext={next} />
  if (step === 1) return <LinkStep onPrev={prev} onNext={next} />
  return <ReadyStep prefs={prefs.data} onPrev={prev} />
}

type StepProps = { onPrev: () => void; onNext: () => void }

function Question({ title, hint }: { title: string; hint: string }) {
  return (
    <>
      <p className={styles.q}>{title}</p>
      <p className={`meta ${styles.hint}`}>{hint}</p>
    </>
  )
}

// 1단계: 조건 네 가지. "다음"을 누르면 저장한다(피하고 싶은 시간을 에이전트가 다듬느라 조금 걸릴 수 있다)
function PrefStep({ initial, onSkip, onNext }: { initial: Preferences; onSkip: () => void; onNext: () => void }) {
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
          <button type="button" className="btn quiet" disabled={saving} onClick={onSkip}>
            나중에 하기
          </button>
          <button type="button" className="btn primary" disabled={saving} onClick={next}>
            {saving ? '저장하는 중…' : '다음'}
          </button>
        </div>
      }
    >
      <Question title="회의 조건 설정" hint="모든 항목은 선택이며 My 탭에서 변경할 수 있습니다." />
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
function LinkStep({ onPrev, onNext }: StepProps) {
  const user = useCurrentUser()
  const today = toIsoDate(useClock())
  const week = useApi(() => getMyWeek(user.roomId, today), [user.roomId, user.id, today])
  const [adding, setAdding] = useState<Recurrence | null>(null)
  const linked = week.status === 'ready' && week.data.blocks.some((b) => b.source !== null)

  return (
    <Screen
      title={TITLE}
      onBack={onPrev}
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
      <Question title="일정 연결" hint="등록한 일정 시간은 조율에서 제외됩니다." />
      <section className="sec">
        {week.status === 'error' && <RetryBox message={week.message} onRetry={week.reload} />}
        {week.status === 'ready' && (
          <ScheduleLinks
            blocks={week.data.blocks}
            onAdd={(recurrence) => {
              setAdding(recurrence)
            }}
          />
        )}
        {adding && (
          <ScheduleForm
            recurrence={adding}
            onCancel={() => setAdding(null)}
            onSaved={(message) => {
              setAdding(null)
              showNotice(message)
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
      onBack={onPrev}
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
      <Question title="설정 완료" hint="에이전트는 위 조건으로 조율에 참여합니다." />
      <AgentQuote name={user.name} prefs={prefs} />
    </Screen>
  )
}
