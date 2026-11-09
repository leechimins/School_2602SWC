import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError, messageOf } from '../api/client.ts'
import { joinRoom, previewInvite } from '../api/rooms.ts'
import { signIn } from '../api/session.ts'
import Screen from '../components/Screen.tsx'
import { PATHS } from '../lib/paths.ts'
import type { InvitePreview } from '../types/room.ts'
import form from './Form.module.css'

const CODE_LENGTH = 6 // 초대 코드는 6자리(room/schemas.py JoinIn)

// 초대 코드로 들어가기(팀원 1회): 코드 → 어떤 방인지 확인 → 들어가기 → 내 조건 알려 주기(온보딩).
// 방 이름과 인원을 먼저 보여 줘서 잘못 받은 코드로 엉뚱한 방에 들어가지 않게 한다.
export default function JoinPage() {
  const navigate = useNavigate()
  const [code, setCode] = useState('')
  const [found, setFound] = useState<InvitePreview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [alreadyIn, setAlreadyIn] = useState(false)
  const [busy, setBusy] = useState(false)

  const typed = code.trim().toUpperCase()
  const full = found !== null && found.joinedCount >= found.memberCount

  const changeCode = (value: string) => {
    setCode(value.toUpperCase().replace(/[^0-9A-Z]/g, '').slice(0, CODE_LENGTH))
    setFound(null) // 코드를 고치면 찾은 방은 다시 찾아야 한다
    setError(null)
    setAlreadyIn(false)
  }

  const find = async () => {
    if (typed.length !== CODE_LENGTH) return setError(`초대 코드 ${CODE_LENGTH}자리를 써 주세요.`)
    setBusy(true)
    try {
      setFound(await previewInvite(typed))
      setError(null)
    } catch (e) {
      setError(messageOf(e))
    } finally {
      setBusy(false)
    }
  }

  const join = async () => {
    setBusy(true)
    try {
      await joinRoom(typed)
      await signIn(null) // 실서버: 내 방 번호를 다시 받는다. 이제야 방이 생겼다
      navigate(PATHS.onboarding, { replace: true })
    } catch (e) {
      // 이미 팀원이면 막을 일이 아니라 홈으로 보내 주면 된다
      setAlreadyIn(e instanceof ApiError && e.code === 'ALREADY_MEMBER')
      setError(messageOf(e))
      setBusy(false)
    }
  }

  const dock = found ? (
    <div className="btn-row">
      <button type="button" className="btn quiet" disabled={busy} onClick={() => changeCode('')}>
        다른 코드
      </button>
      {alreadyIn ? (
        <Link to={PATHS.home} className="btn primary">
          홈으로
        </Link>
      ) : (
        <button type="button" className="btn primary" disabled={busy || full} onClick={join}>
          이 방에 들어가기
        </button>
      )}
    </div>
  ) : (
    <div className="btn-row">
      <button type="button" className="btn primary" disabled={busy} onClick={find}>
        방 찾기
      </button>
    </div>
  )

  return (
    <Screen title="초대 코드로 들어가기" dock={dock}>
      <section className="sec">
        <label className={form.label}>
          초대 코드
          <input
            className={`field num ${form.code}`}
            value={code}
            inputMode="text"
            autoCapitalize="characters"
            autoComplete="off"
            spellCheck={false}
            placeholder="T9K2QM"
            aria-describedby="join-help"
            onChange={(e) => changeCode(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !found && find()}
          />
        </label>
        <p id="join-help" className="meta">
          팀장에게 받은 {CODE_LENGTH}자리 코드를 써 주세요.
        </p>
        {error && (
          <p className={form.error} role="alert">
            {error}
          </p>
        )}
      </section>

      {found && (
        <section className="sec">
          <h2>{found.name}</h2>
          <p className="meta num">
            팀원 {found.joinedCount}/{found.memberCount}명 들어와 있어요
          </p>
          {full && <p className={form.error}>팀원 수가 다 찼어요. 팀장에게 확인해 주세요.</p>}
        </section>
      )}

      <p className={`meta ${form.hint}`}>
        들어가면 내 조건을 알려 주고 일정을 연결해요. 팀을 직접 꾸린다면{' '}
        <Link to={PATHS.start} className="link">
          방 만들기
        </Link>
      </p>
    </Screen>
  )
}
