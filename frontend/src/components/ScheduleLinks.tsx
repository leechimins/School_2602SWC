import { useRef, useState, type ChangeEvent, type ReactNode } from 'react'
import { ApiError, messageOf } from '../api/client.ts'
import { connectEverytime, connectGoogle, readEverytimeCapture } from '../api/me.ts'
import { showNotice } from '../lib/notice.ts'
import type { CapturedClass, LinkResult, Recurrence, WeekBlock } from '../types/me.ts'
import CaptureSheet from './CaptureSheet.tsx'
import Sheet from './Sheet.tsx'
import styles from './ScheduleLinks.module.css'

type Props = {
  blocks: WeekBlock[] // 이번 주 내 시간표. 어디서 온 일정이 있는지로 연결 여부를 본다
  onAdd: (recurrence: Recurrence) => void // "직접 추가"를 누르면 그 묶음(매주 반복·한 번만)의 추가 시트를 연다
  showLock?: boolean // 바쁨/비어 있음 안내. My 탭에서는 끈다
}

type Reading = { state: 'idle' } | { state: 'reading' } | { state: 'fail'; message: string }
// 에타 결과에만 붙는 덧말. past: 지난 학기 시간표라 이번 학기 링크를 다시 받는다 / manual: 서버에 연동이 없어 다시 하기 대신 직접 추가로
type EtNote = 'past' | 'manual' | null

// 내 일정 가져오기: 같은 모양의 줄 세 개(이름·설명 | 오른쪽 동작)
//   에브리타임 시간표 — 매주 반복 수업. [불러오기]는 링크·캡처를 고르는 아래 시트를 연다
//   구글 캘린더       — 그날만 있는 약속. [연결]
//   직접 추가         — 앱 밖 일정(알바·약속). [매주] [한 번만]
// 연동이 끝난 줄은 누를 수 없는 "연동됨"과 설명 옆 "다시 불러오기"가 보인다. 결과는 아래 한 줄(showNotice)로 알린다
export default function ScheduleLinks({ blocks, onAdd, showLock = true }: Props) {
  const [etOpen, setEtOpen] = useState(false) // 에타 불러오기 시트
  const [gc, setGc] = useState<Reading>({ state: 'idle' })
  const [googleDone, setGoogleDone] = useState(false) // 이번 주에 약속이 없어도 방금 연결했으면 연동됨
  const [captured, setCaptured] = useState<CapturedClass[] | null>(null) // AI가 읽은 수업. 있으면 확인 시트를 연다

  const classCount = new Set(blocks.filter((b) => b.source === 'everytime').map((b) => b.title)).size
  const googleOn = googleDone || blocks.some((b) => b.source === 'google')

  // 구글 팝업은 클릭 직후에 열려야 막히지 않는다. connectGoogle을 다른 await보다 먼저 부른다
  const linkGoogle = async () => {
    setGc({ state: 'reading' })
    try {
      const { count } = await connectGoogle()
      setGc({ state: 'idle' })
      setGoogleDone(true)
      showNotice(`팀플 마감까지 약속 ${count}개를 가져왔어요`)
    } catch (e) {
      setGc({ state: 'fail', message: messageOf(e) })
    }
  }

  return (
    <>
      <LinkRow
        name="에브리타임 시간표"
        detail={classCount > 0 ? `수업 ${classCount}개` : '매주 반복되는 수업'}
        on={classCount > 0}
        busy={false}
        label="불러오기"
        onLink={() => setEtOpen(true)}
      />

      <LinkRow name="구글 캘린더" detail="그날만 있는 약속" on={googleOn} busy={gc.state === 'reading'} label="연결" onLink={linkGoogle}>
        {gc.state === 'reading' && <p className={`meta ${styles.msg}`}>구글 창에서 허락하면 약속을 읽어 와요…</p>}
        {gc.state === 'fail' && (
          <p className={`${styles.msg} ${styles.bad}`} role="alert">
            {gc.message}
          </p>
        )}
      </LinkRow>

      <div className={styles.row}>
        <div>
          <p className="strong">직접 추가</p>
          <p className="meta">알바·약속처럼 앱 밖 일정</p>
        </div>
        <div className={styles.pair}>
          <button type="button" className="btn small" onClick={() => onAdd('weekly')}>
            매주
          </button>
          <button type="button" className="btn small" onClick={() => onAdd('once')}>
            한 번만
          </button>
        </div>
      </div>

      {etOpen && (
        <EverytimeSheet
          onClose={() => setEtOpen(false)}
          onCaptured={(classes) => {
            setEtOpen(false)
            setCaptured(classes)
          }}
          onManual={() => {
            setEtOpen(false)
            onAdd('weekly')
          }}
        />
      )}
      {captured && (
        <CaptureSheet
          classes={captured}
          onClose={() => setCaptured(null)}
          onSaved={(result) => {
            setCaptured(null)
            showNotice(loadedMessage(result))
          }}
        />
      )}

      {showLock && (
        <p className={styles.lock}>
          팀원에게는 <b>바쁨 / 비어 있음</b>만 보여요. 약속 이름은 아무도 못 봐요.
        </p>
      )}
    </>
  )
}

const loadedMessage = ({ count, term }: LinkResult) => `${term ? `${term} ` : ''}수업 ${count}개를 가져왔어요`

// 연동 한 줄: 이름·설명(+ 연동됐으면 "다시 불러오기") | [버튼] 또는 누를 수 없는 "연동됨"
type LinkRowProps = {
  name: string
  detail: string
  on: boolean
  busy: boolean
  label: string
  onLink: () => void
  children?: ReactNode // 이름 아래 진행·실패 글
}

function LinkRow({ name, detail, on, busy, label, onLink, children }: LinkRowProps) {
  return (
    <div className={styles.row}>
      <div>
        <p className="strong">{name}</p>
        <p className="meta">
          {detail}
          {on && (
            <>
              {' · '}
              <button type="button" className={`link ${styles.again}`} disabled={busy} onClick={onLink}>
                다시 불러오기
              </button>
            </>
          )}
        </p>
        {children}
      </div>
      {on ? (
        <span className={`btn small ${styles.done}`}>연동됨</span>
      ) : (
        <button type="button" className="btn small" disabled={busy} onClick={onLink}>
          {label}
        </button>
      )}
    </div>
  )
}

type EverytimeSheetProps = {
  onClose: () => void
  onCaptured: (classes: CapturedClass[]) => void
  onManual: () => void // 서버에 에타 연동이 없을 때 수업 직접 넣기로
}

// 에브리타임 불러오기 시트: 공유 링크 칸 + [캡처로 올리기]. 링크로 가져오면 닫고 아래 한 줄로 알린다.
// 캡처는 읽기만 하고 저장하지 않는다. 읽은 수업은 확인 시트(CaptureSheet)에서 고친 뒤 넣는다(#66)
function EverytimeSheet({ onClose, onCaptured, onManual }: EverytimeSheetProps) {
  const [url, setUrl] = useState('')
  const [et, setEt] = useState<Reading>({ state: 'idle' })
  const [note, setNote] = useState<EtNote>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const reading = et.state === 'reading'

  const loadLink = async () => {
    setEt({ state: 'reading' })
    setNote(null)
    try {
      const result = await connectEverytime(url.trim())
      if (result.termState === 'past') {
        setEt({ state: 'idle' })
        return setNote('past') // 지난 학기면 닫지 않고 이번 학기 링크를 다시 받는다
      }
      showNotice(loadedMessage(result))
      onClose()
    } catch (e) {
      setEt({ state: 'fail', message: messageOf(e) })
      if (e instanceof ApiError && e.code === 'EVERYTIME_NOT_CONFIGURED') setNote('manual')
    }
  }

  const readCapture = async (e: ChangeEvent<HTMLInputElement>) => {
    const image = e.target.files?.[0]
    e.target.value = '' // 같은 파일을 다시 골라도 다시 읽게
    if (!image) return
    setEt({ state: 'reading' })
    setNote(null)
    try {
      const classes = await readEverytimeCapture(image)
      if (classes.length === 0) return setEt({ state: 'fail', message: '캡처에서 수업을 찾지 못했어요. 시간표 전체가 보이게 다시 찍어 주세요.' })
      onCaptured(classes)
    } catch (err) {
      setEt({ state: 'fail', message: messageOf(err) })
    }
  }

  return (
    <Sheet
      title="에브리타임 시간표"
      onClose={onClose}
      actions={
        <>
          <button type="button" className="btn quiet" onClick={onClose}>
            취소
          </button>
          <button type="button" className="btn primary" disabled={!url.trim() || reading} onClick={loadLink}>
            {reading ? '읽는 중…' : '불러오기'}
          </button>
        </>
      }
    >
      <input
        className={`field num ${styles.url}`}
        value={url}
        placeholder="에타 시간표 → 공유 → 링크 복사"
        aria-label="에브리타임 공유 링크"
        autoFocus
        onChange={(e) => setUrl(e.target.value)}
      />
      <button type="button" className={`btn block ${styles.capture}`} disabled={reading} onClick={() => fileRef.current?.click()}>
        캡처로 올리기
      </button>
      <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={readCapture} />
      {et.state === 'fail' && (
        <p className={`${styles.msg} ${styles.bad}`} role="alert">
          {et.message}
        </p>
      )}
      {note === 'past' && (
        <p className={`${styles.msg} ${styles.warn}`} role="alert">
          지난 학기 시간표예요. 이번 학기 시간표 링크를 넣어 주세요.
        </p>
      )}
      {note === 'manual' && (
        <button type="button" className={`link ${styles.msg}`} onClick={onManual}>
          수업 직접 넣기
        </button>
      )}
    </Sheet>
  )
}
