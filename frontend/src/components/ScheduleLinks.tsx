import { useRef, useState, type ChangeEvent, type CSSProperties, type ReactNode } from 'react'
import { ApiError, messageOf } from '../api/client.ts'
import { connectEverytime, connectGoogle, readEverytimeCapture } from '../api/me.ts'
import type { CapturedClass, LinkResult, Recurrence, WeekBlock } from '../types/me.ts'
import CaptureSheet from './CaptureSheet.tsx'
import styles from './ScheduleLinks.module.css'

type Props = {
  blocks: WeekBlock[] // 이번 주 내 시간표. 어디서 온 일정이 있는지로 연결 여부를 본다
  onAdd: (recurrence: Recurrence) => void // 일정 추가 시트를 연다. 시트 안에서 한 번만·매주 반복을 바꿀 수 있다
  title?: string // 주면 카드 제목 줄(제목 | 연결 수)을 그린다. My 탭이 쓴다
  showLock?: boolean // 바쁨/비어 있음 안내. My 탭에서는 끈다
}

type Reading = { state: 'idle' } | { state: 'reading' } | { state: 'ok' | 'fail'; message: string }
// 에타 결과에만 붙는 덧말. past: 지난 학기 시간표라 이번 학기 링크를 다시 받는다 / manual: 서버에 연동이 없어 다시 하기 대신 직접 추가로
type EtNote = 'past' | 'manual' | null

// 일정 가져오기: 위에 연결 수와 막대(연동 두 개 중 몇 개), 아래 설정 목록 세 줄.
// 줄 왼쪽 점이 연결 상태다 — 채운 점 = 연결됨, 빈 점 = 아직. 줄 전체를 누른다
//   에브리타임 시간표: 누르면 그 아래에 링크 칸 · 캡처로 올리기가 열린다
//   구글 캘린더: 누르면 구글 연결 팝업. 연결되면 "연결됨"
//   일정 추가: 누르면 시트(한 번만 / 매주 반복)
// 성공·실패 문구는 그 줄 아래 한 줄로 보인다
export default function ScheduleLinks({ blocks, onAdd, title, showLock = true }: Props) {
  const [url, setUrl] = useState('')
  const [etOpen, setEtOpen] = useState(false)
  const [et, setEt] = useState<Reading>({ state: 'idle' })
  const [etNote, setEtNote] = useState<EtNote>(null)
  const [gc, setGc] = useState<Reading>({ state: 'idle' })
  const [captured, setCaptured] = useState<CapturedClass[] | null>(null) // AI가 읽은 수업. 있으면 확인 시트를 연다
  const fileRef = useRef<HTMLInputElement>(null)

  const classCount = new Set(blocks.filter((b) => b.source === 'everytime').map((b) => b.title)).size
  const googleCount = blocks.filter((b) => b.source === 'google').length

  const showLoaded = ({ count, term, termState }: LinkResult) => {
    setEt({ state: 'ok', message: `${term ? `${term} ` : ''}수업 ${count}개를 가져왔어요` })
    if (termState === 'past') setEtNote('past')
    setEtOpen(false)
    setUrl('')
  }
  const loadEverytime = async () => {
    setEt({ state: 'reading' })
    setEtNote(null)
    try {
      showLoaded(await connectEverytime(url.trim()))
    } catch (e) {
      setEt({ state: 'fail', message: messageOf(e) })
      if (e instanceof ApiError && e.code === 'EVERYTIME_NOT_CONFIGURED') setEtNote('manual')
    }
  }
  // 캡처는 읽기만 하고 저장하지 않는다. 읽은 수업은 확인 시트에서 고친 뒤 넣는다(#66)
  const readCapture = async (e: ChangeEvent<HTMLInputElement>) => {
    const image = e.target.files?.[0]
    e.target.value = '' // 같은 파일을 다시 골라도 다시 읽게
    if (!image) return
    setEt({ state: 'reading' })
    setEtNote(null)
    try {
      const classes = await readEverytimeCapture(image)
      if (classes.length === 0) return setEt({ state: 'fail', message: '캡처에서 수업을 찾지 못했어요. 시간표 전체가 보이게 다시 찍어 주세요.' })
      setEt({ state: 'idle' })
      setCaptured(classes)
    } catch (err) {
      setEt({ state: 'fail', message: messageOf(err) })
    }
  }
  // 구글 팝업은 클릭 직후에 열려야 막히지 않는다. connectGoogle을 다른 await보다 먼저 부른다
  const linkGoogle = async () => {
    setGc({ state: 'reading' })
    try {
      const { count } = await connectGoogle()
      setGc({ state: 'ok', message: `팀플 마감까지 약속 ${count}개를 가져왔어요` })
    } catch (e) {
      setGc({ state: 'fail', message: messageOf(e) })
    }
  }
  const etOn = classCount > 0 || et.state === 'ok'
  const googleOn = googleCount > 0 || gc.state === 'ok' // 이번 주에 약속이 없어도 방금 연결했으면 켜짐
  const linked = Number(etOn) + Number(googleOn)

  const etNotes = (et.state === 'ok' || et.state === 'fail' || etNote) && (
    <>
      {note(et)}
      {etNote === 'past' && (
        <span className={styles.warn} role="alert">
          지난 학기 시간표예요. 이번 학기 시간표 링크를 넣어 주세요.
        </span>
      )}
      {etNote === 'manual' && (
        <button type="button" className={`link ${styles.inline}`} onClick={() => onAdd('weekly')}>
          수업 직접 넣기
        </button>
      )}
    </>
  )

  return (
    <>
      {title && (
        <div className="row-between">
          <h2>{title}</h2>
          <span className={`num ${styles.count}`}>
            <b>{linked}</b>/2 연결
          </span>
        </div>
      )}
      {/* 연결 막대: 연동 두 개 중 몇 개. 덜 찬 칸이 "아직 남았다"를 보여 준다 */}
      <div className={styles.bar} role="img" aria-label={`연동 2개 중 ${linked}개 연결`}>
        <i style={{ '--fill': `${(linked / 2) * 100}%` } as CSSProperties} />
      </div>

      <ul className={styles.list}>
        <Row
          dot={etOn ? 'on' : 'off'}
          title="에브리타임 시간표"
          value={et.state === 'reading' ? '읽는 중…' : classCount > 0 ? `수업 ${classCount}개` : '가져오기'}
          on={etOn}
          expanded={etOpen}
          onPress={() => setEtOpen(!etOpen)}
          note={etNotes}
        >
          {etOpen && (
            <>
              <div className={styles.input}>
                <input
                  className="field num"
                  value={url}
                  placeholder="에타 시간표 → 공유 → 링크 복사"
                  aria-label="에브리타임 공유 링크"
                  autoFocus
                  onChange={(e) => setUrl(e.target.value)}
                />
                <button type="button" className="btn small primary" disabled={!url.trim() || et.state === 'reading'} onClick={loadEverytime}>
                  불러오기
                </button>
              </div>
              <button type="button" className={`link ${styles.inline}`} disabled={et.state === 'reading'} onClick={() => fileRef.current?.click()}>
                캡처로 올리기
              </button>
            </>
          )}
        </Row>

        <Row
          dot={googleOn ? 'on' : 'off'}
          title="구글 캘린더"
          value={gc.state === 'reading' ? '연결 중…' : googleOn ? '연결됨' : '연결 안 됨'}
          on={googleOn}
          onPress={googleOn || gc.state === 'reading' ? undefined : linkGoogle}
          note={note(gc)}
        />

        <Row dot="add" title="일정 추가" value={null} mark="" onPress={() => onAdd('once')} />
      </ul>
      <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={readCapture} />

      {captured && (
        <CaptureSheet
          classes={captured}
          onClose={() => setCaptured(null)}
          onSaved={(result) => {
            setCaptured(null)
            showLoaded(result)
          }}
        />
      )}

      {showLock && (
        <p className={styles.lock}>
          팀원에게는 <b>바쁨 / 비어 있음</b>만 보여요. 약속 이름은 나만 봐요.
        </p>
      )}
    </>
  )
}

// 줄 아래 한 줄: 방금 성공·실패한 문구
function note(r: Reading): ReactNode {
  if (r.state === 'fail')
    return (
      <span className={styles.bad} role="alert">
        {r.message}
      </span>
    )
  if (r.state === 'ok') return <span role="status">{r.message}</span>
  return null
}

type RowProps = {
  dot: 'on' | 'off' | 'add' // 왼쪽 표시: 채운 점(연결됨) · 빈 점(아직) · +(추가)
  title: string
  value: string | null // 오른쪽 상태 글자
  on?: boolean // 연결돼 있으면 상태 글자를 포인트색으로
  mark?: string // 오른쪽 끝 표시. 기본 ›
  expanded?: boolean
  onPress?: () => void // 없으면 누를 수 없는 줄(이미 연결됨)
  note?: ReactNode
  children?: ReactNode
}

function Row({ dot, title, value, on = false, mark = '›', expanded, onPress, note, children }: RowProps) {
  const inner = (
    <>
      <span className={styles.dot} data-k={dot} aria-hidden="true">
        {dot === 'add' ? '+' : ''}
      </span>
      <span className={`strong ${styles.title}`}>{title}</span>
      {value && <span className={`${styles.value} ${on ? styles.on : ''}`}>{value}</span>}
      <span className={styles.mark} aria-hidden="true">
        {onPress ? mark : ''}
      </span>
    </>
  )
  return (
    <li className={styles.item}>
      {onPress ? (
        <button type="button" className={styles.row} aria-expanded={expanded} onClick={onPress}>
          {inner}
        </button>
      ) : (
        <div className={styles.row}>{inner}</div>
      )}
      {note && <div className={styles.note}>{note}</div>}
      {children && <div className={styles.full}>{children}</div>}
    </li>
  )
}
