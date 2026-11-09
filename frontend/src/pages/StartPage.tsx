import dayjs from 'dayjs'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError, isRealServer, messageOf } from '../api/client.ts'
import { createRoom, getRoom, joinRoom, previewInvite } from '../api/rooms.ts'
import { signIn } from '../api/session.ts'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import Segmented from '../components/Segmented.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { PATHS } from '../lib/paths.ts'
import type { InvitePreview, Room, RoomInput } from '../types/room.ts'
import form from './Form.module.css'

const TEAM_SIZES = [2, 3, 4, 5, 6] as const // 팀은 2~6명

const WAYS = ['초대 코드로 들어가기', '방 만들기'] as const
type Way = (typeof WAYS)[number]

// 방 생성하기(팀장 1회): 과제 제목·설명·기간·팀원 수 → 초대 코드 → 온보딩.
// 시연에서 바로 넘어가도록 지금 방의 값을 미리 채워 둔다.
// 아직 방이 없는 사람(구글로 처음 온 사람)에게는 "초대 코드로 들어가기 | 방 만들기" 두 갈래를 보여 준다.
// 처음 오는 사람은 대부분 팀원이라(팀장은 한 명) 들어가기가 먼저다.
export default function StartPage() {
  const user = useCurrentUser()
  const noRoom = isRealServer() && !user.roomId
  const [way, setWay] = useState<Way>(noRoom ? '초대 코드로 들어가기' : '방 만들기')
  const room = useApi<RoomInput>(() => (user.roomId ? getRoom(user.roomId) : Promise.resolve(blankRoom())), [user.roomId])
  const [created, setCreated] = useState<Room | null>(null)

  const switcher = noRoom ? (
    <div className={form.ways}>
      <Segmented label="시작 방법" options={WAYS} value={way} onChange={setWay} />
    </div>
  ) : null

  if (created) return <Created room={created} />
  if (way === '초대 코드로 들어가기') return <JoinForm switcher={switcher} />
  if (room.status === 'ready') return <RoomForm initial={room.data} onCreated={setCreated} switcher={switcher} />
  return (
    <Screen title="방 만들기">
      {switcher}
      {room.status === 'error' && <RetryBox message={room.message} onRetry={room.reload} />}
    </Screen>
  )
}

function blankRoom(): RoomInput {
  const today = dayjs()
  return { name: '', description: '', startDate: today.format('YYYY-MM-DD'), dueDate: today.add(6, 'week').format('YYYY-MM-DD'), memberCount: 4 }
}

function RoomForm({ initial, onCreated, switcher }: { initial: RoomInput; onCreated: (room: Room) => void; switcher: ReactNode }) {
  const [input, setInput] = useState<RoomInput>({
    name: initial.name,
    description: initial.description,
    startDate: initial.startDate,
    dueDate: initial.dueDate,
    memberCount: initial.memberCount,
  })
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const set = <K extends keyof RoomInput>(key: K, value: RoomInput[K]) => setInput((prev) => ({ ...prev, [key]: value }))

  const problem = !input.name.trim()
    ? '과제 제목을 써 주세요.'
    : input.startDate > input.dueDate
      ? '마감일이 시작일보다 빨라요.'
      : null

  const submit = async () => {
    if (problem) return setError(problem)
    setSaving(true)
    try {
      const room = await createRoom({ ...input, name: input.name.trim(), description: input.description.trim() })
      await signIn(null) // 실서버: 내 방 번호를 다시 받는다. 처음 온 사람은 이제야 방이 생겼다
      onCreated(room)
    } catch (e) {
      setError(messageOf(e))
      setSaving(false)
    }
  }

  return (
    <Screen
      title="방 만들기"
      dock={
        <div className="btn-row">
          <button type="button" className="btn primary" disabled={saving} onClick={submit}>
            방 만들기
          </button>
        </div>
      }
    >
      {switcher}
      <section className="sec">
        <label className={form.label}>
          과제 제목 (방 이름)
          <input className="field" value={input.name} maxLength={40} onChange={(e) => set('name', e.target.value)} />
        </label>
        <label className={form.label}>
          과제 설명
          <textarea
            className={`field ${form.textarea}`}
            rows={3}
            maxLength={200}
            value={input.description}
            placeholder="무엇을 만들고 어떻게 평가받는지 두세 줄로 써 주세요"
            onChange={(e) => set('description', e.target.value)}
          />
        </label>
        <span className={form.label}>기간</span>
        <div className={form.range}>
          <input className="field num" type="date" aria-label="시작일" value={input.startDate} onChange={(e) => set('startDate', e.target.value)} />
          <span>–</span>
          <input className="field num" type="date" aria-label="마감일" value={input.dueDate} onChange={(e) => set('dueDate', e.target.value)} />
        </div>
        <span className={form.label}>팀원 수</span>
        <Segmented
          label="팀원 수"
          options={TEAM_SIZES}
          value={input.memberCount as (typeof TEAM_SIZES)[number]}
          format={(n) => `${n}명`}
          onChange={(n) => set('memberCount', n)}
        />
        {error && (
          <p className={form.error} role="alert">
            {error}
          </p>
        )}
      </section>
      <p className={`meta ${form.hint}`}>방을 만든 사람이 팀장이 되고, 회의 잡기는 팀장만 할 수 있어요.</p>
    </Screen>
  )
}

// 초대 코드로 들어가기(팀원): 코드 6자리 → 어떤 방인지 미리보기 → 들어가기 → 온보딩
function JoinForm({ switcher }: { switcher: ReactNode }) {
  const navigate = useNavigate()
  const [code, setCode] = useState('')
  const [preview, setPreview] = useState<InvitePreview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [joining, setJoining] = useState(false)
  const full = preview !== null && preview.joinedCount >= preview.memberCount

  // 6자리가 다 차면 어떤 방인지 바로 보여 준다
  useEffect(() => {
    if (code.length !== 6) return
    const run = { alive: true } // 코드를 고치는 사이 늦게 온 지난 답이 덮지 않게
    previewInvite(code).then(
      (p) => run.alive && setPreview(p),
      (e: unknown) => run.alive && setError(messageOf(e)),
    )
    return () => {
      run.alive = false
    }
  }, [code])

  const onCode = (value: string) => {
    setCode(value.replace(/[^0-9a-z]/gi, '').toUpperCase().slice(0, 6))
    setPreview(null)
    setError(null)
  }

  const join = async () => {
    setJoining(true)
    setError(null)
    try {
      await joinRoom(code)
      await signIn(null) // 실서버: 내 방 번호를 다시 받는다
      navigate(PATHS.onboarding, { replace: true })
    } catch (e) {
      if (e instanceof ApiError && e.code === 'ALREADY_MEMBER') {
        await signIn(null) // 이미 팀원이다: 막을 일이 아니라 그냥 들어간다
        return navigate(PATHS.home, { replace: true })
      }
      setError(messageOf(e))
      setJoining(false)
    }
  }

  return (
    <Screen
      title="방 들어가기"
      dock={
        <div className="btn-row">
          <button type="button" className="btn primary" disabled={!preview || full || joining} onClick={join}>
            {joining ? '들어가는 중…' : '이 방에 들어가기'}
          </button>
        </div>
      }
    >
      {switcher}
      <section className="sec">
        <label className={form.label}>
          초대 코드
          <input
            className={`field num ${form.codeInput}`}
            value={code}
            maxLength={6}
            autoCapitalize="characters"
            autoComplete="off"
            spellCheck={false}
            placeholder="6자리"
            onChange={(e) => onCode(e.target.value)}
          />
        </label>
        {error && (
          <p className={form.error} role="alert">
            {error}
          </p>
        )}
      </section>
      {preview && (
        <section className="sec">
          <h2>{preview.name}</h2>
          <p className="meta num">
            {full ? '팀원 수가 다 찼어요. 팀장에게 확인해 주세요.' : `${preview.joinedCount}/${preview.memberCount}명 들어와 있어요`}
          </p>
        </section>
      )}
      <p className={`meta ${form.hint}`}>팀장에게 받은 초대 코드를 넣어 주세요. 들어간 뒤 내 조건을 알려 주면 에이전트가 대신 말해요.</p>
    </Screen>
  )
}

// 만든 뒤: 초대 코드를 보내고 내 조건 알려 주기(온보딩)로 넘어간다
function Created({ room }: { room: Room }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(room.inviteCode)
      setCopied(true)
    } catch {
      setCopied(false) // 복사가 막힌 브라우저에서는 코드를 보고 직접 알려 주면 된다
    }
  }

  return (
    <Screen
      title="방을 만들었어요"
      dock={
        <div className="btn-row">
          <Link to={PATHS.home} className="btn quiet">
            홈으로
          </Link>
          <Link to={PATHS.onboarding} className="btn primary">
            다음: 내 조건 알려 주기
          </Link>
        </div>
      }
    >
      <section className="sec">
        <h2>{room.name}</h2>
        <p className="meta">팀원에게 이 코드를 보내 주세요. 팀원은 초대 코드로 들어와요.</p>
        <div className="row-between">
          <span className={`${form.code} num`}>{room.inviteCode}</span>
          <button type="button" className="btn small" onClick={copy}>
            {copied ? '복사했어요' : '코드 복사'}
          </button>
        </div>
      </section>
    </Screen>
  )
}
