import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { isRealServer, messageOf } from '../api/client.ts'
import { getIdentity, signIn, signInWithGoogle } from '../api/session.ts'
import { currentUserName } from '../hooks/useCurrentUser.ts'
import { markBooted } from '../lib/boot.ts'
import { PATHS } from '../lib/paths.ts'
import styles from './SplashPage.module.css'

const SPLASH_MS = 2000 // 로그인돼 있을 때 캐릭터를 보여 주는 시간
const BUTTON_MS = 1000 // 로그인이 필요할 때 버튼이 나타나기까지
const LEAVE_MS = 450 // 들어갈 때 스플래시가 걷히는 시간 (SplashPage.module.css .leaving과 같게)
const CLIENT_ID = (import.meta.env.VITE_GOOGLE_CLIENT_ID ?? '').trim()

// 스플래시 + 구글 로그인. 앱을 열면 캐릭터가 둥둥 뜨고,
// 로그인돼 있으면(쿠키) 2초 뒤 원래 가려던 곳으로, 아니면 1초 뒤 캐릭터 아래에 로그인 버튼이 나타난다.
export default function SplashPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from ?? PATHS.home
  const [needLogin, setNeedLogin] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [leaving, setLeaving] = useState(false)

  // 로그인이 끝났다: 방이 없으면(구글로 처음 온 사람) 방 만들기, 있으면 원래 가려던 곳.
  // 바로 바꾸면 화면이 확 바뀌어서, 스플래시를 먼저 흐리게 걷고(LEAVE_MS) 넘어간다. 앱 틀은 들어오며 페이드인한다(AppShell).
  const enter = (isNew = false) => {
    const noRoom = isRealServer() && !getIdentity()?.roomId
    setLeaving(true)
    document.body.classList.remove('brand') // 걷히는 동안 뒤에 비치는 색을 앱 바탕 쪽으로
    window.setTimeout(() => {
      markBooted()
      navigate(isNew || noRoom ? PATHS.start : from, { replace: true })
    }, LEAVE_MS)
  }
  const enterRef = useRef(enter)
  useLayoutEffect(() => {
    enterRef.current = enter
  })

  // 넓은 화면에서 앱 틀 양옆도 같은 보라로 (평소에는 --frame 회색)
  useEffect(() => {
    document.body.classList.add('brand')
    return () => document.body.classList.remove('brand')
  }, [])

  useEffect(() => {
    const opened = Date.now() // 두 시간 모두 화면이 열린 때부터 잰다
    const timers: number[] = []
    const after = (ms: number, fn: () => void) => timers.push(window.setTimeout(fn, Math.max(0, ms - (Date.now() - opened))))
    const run = { alive: true } // 화면을 떠난 뒤 늦게 끝나도 이동하지 않게
    void signIn(null).then(() => {
      if (!run.alive) return
      // 목 모드거나 서버가 안 닿아 목으로 넘어갔으면 로그인 없이 들어간다
      if (!isRealServer() || getIdentity()) after(SPLASH_MS, () => enterRef.current())
      else after(BUTTON_MS, () => setNeedLogin(true))
    })
    return () => {
      run.alive = false
      timers.forEach(clearTimeout)
    }
  }, [])

  const onGoogle = async (credential: string) => {
    setBusy(true)
    setError(null)
    try {
      enterRef.current(await signInWithGoogle(credential))
    } catch (e) {
      setError(messageOf(e))
      setBusy(false)
    }
  }

  const onDemo = async () => {
    setBusy(true)
    setError(null)
    await signIn(currentUserName()) // 시드의 팀장으로 들어간다
    if (!isRealServer() || getIdentity()) return enterRef.current()
    setError('시연 계정으로 들어가지 못했어요. 서버에 시드가 들어 있는지 확인해 주세요.')
    setBusy(false)
  }

  return (
    <main className={`${styles.page} ${leaving ? styles.leaving : ''}`}>
      <div className={styles.hero}>
        {/* 그림 파일이 없으면 깨진 아이콘 대신 배경만 둔다 */}
        <img className={styles.art} src="/splash/ttak.webp" alt="TTAK" onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
        <div className={styles.shadow} aria-hidden="true" />
      </div>

      {/* 버튼 자리는 처음부터 비워 둔다 — 버튼이 나타나도 캐릭터가 움직이지 않게 */}
      <section className={styles.actions} aria-label="로그인">
        {needLogin && (
          <div className={styles.appear}>
            <GoogleButton disabled={busy} onCredential={onGoogle} />
            {error && (
              <p className={styles.error} role="alert">
                {error}
              </p>
            )}
            <button type="button" className={styles.demo} disabled={busy} onClick={onDemo}>
              시연 계정으로 둘러보기
            </button>
          </div>
        )}
      </section>
    </main>
  )
}

// "Google로 로그인" 버튼. 보이는 것은 시안대로 직접 그린 버튼이고, 그 위에 구글 공식 버튼(GSI)을 투명하게 겹친다.
// 공식 버튼은 모양·문구를 바꿀 수 없는데, ID 토큰(서버 POST /sessions/google이 받는 것)은 공식 버튼으로만 받을 수 있어서다.
// 스크립트(index.html)가 늦게 오면 올 때까지 기다리고, 끝내 없으면 버튼을 흐리게 두고 안내 문구를 띄운다.
function GoogleButton({ disabled, onCredential }: { disabled: boolean; onCredential: (credential: string) => void }) {
  const box = useRef<HTMLDivElement>(null)
  const cb = useRef(onCredential)
  useLayoutEffect(() => {
    cb.current = onCredential
  })
  const [state, setState] = useState<'loading' | 'ready' | 'missing'>(CLIENT_ID ? 'loading' : 'missing')

  useEffect(() => {
    if (!CLIENT_ID) return
    const started = Date.now()
    const timer = setInterval(() => {
      const gsi = window.google?.accounts.id
      if (gsi && box.current) {
        clearInterval(timer)
        gsi.initialize({ client_id: CLIENT_ID, callback: (res) => cb.current(res.credential) })
        gsi.renderButton(box.current, {
          theme: 'outline',
          size: 'large',
          shape: 'rectangular',
          text: 'signin_with',
          locale: 'ko',
          width: Math.min(box.current.clientWidth, 400), // 구글이 받는 최대 폭
        })
        setState('ready')
      } else if (Date.now() - started > 5000) {
        clearInterval(timer) // 5초 지나도 없다: 막힌 네트워크
        setState('missing')
      }
    }, 100)
    return () => clearInterval(timer)
  }, [])

  return (
    <>
      <div className={`${styles.google} ${disabled || state !== 'ready' ? styles.dim : ''}`}>
        <span className={styles.gFace} aria-hidden="true">
          <GoogleLogo />
          Google로 로그인
        </span>
        <div ref={box} className={styles.gsi} />
      </div>
      {state === 'missing' && (
        <p className={styles.note}>{CLIENT_ID ? '구글에 연결할 수 없어요. 잠시 뒤 다시 해 주세요.' : '구글 로그인은 아직 설정되지 않았어요.'}</p>
      )}
    </>
  )
}

// 구글 공식 4색 G (브랜드 가이드의 SVG)
function GoogleLogo() {
  return (
    <svg className={styles.gLogo} viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  )
}
