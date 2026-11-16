import { useRef, useState, type ChangeEvent } from 'react'
import { ApiError, messageOf } from '../api/client.ts'
import { connectEverytime, connectGoogle, readEverytimeCapture } from '../api/me.ts'
import type { CapturedClass, LinkResult, Recurrence, WeekBlock } from '../types/me.ts'
import Badge from './Badge.tsx'
import CaptureSheet from './CaptureSheet.tsx'
import styles from './ScheduleLinks.module.css'

type Props = {
  blocks: WeekBlock[] // 이번 주 내 시간표. 어디서 온 일정이 있는지로 연결 여부를 본다
  onAdd: (recurrence: Recurrence) => void // "직접 추가"를 누르면 그 묶음(매주 반복·한 번만)의 추가 시트를 연다
  showLock?: boolean // 바쁨/비어 있음 안내. My 탭에서는 끈다
}

type Reading = { state: 'idle' } | { state: 'reading' } | { state: 'ok' | 'fail'; message: string }
// 에타 결과에만 붙는 덧말. past: 지난 학기 시간표라 이번 학기 링크를 다시 받는다 / manual: 서버에 연동이 없어 다시 하기 대신 직접 추가로
type EtNote = 'past' | 'manual' | null

// 내 일정 가져오기: 같은 모양의 줄 세 개(이름·설명 | 오른쪽 동작)
//   에브리타임 시간표 — 매주 반복 수업. [불러오기]를 누르면 링크 칸·캡처가 펼쳐진다
//   구글 캘린더       — 그날만 있는 약속. [연결]
//   직접 추가         — 앱 밖 일정(알바·약속). [매주] [한 번만]
export default function ScheduleLinks({ blocks, onAdd, showLock = true }: Props) {
  const [url, setUrl] = useState('')
  const [et, setEt] = useState<Reading>({ state: 'idle' })
  const [etNote, setEtNote] = useState<EtNote>(null)
  const [gc, setGc] = useState<Reading>({ state: 'idle' })
  const [etOpen, setEtOpen] = useState(false) // 에타 링크 칸 펼침
  const [captured, setCaptured] = useState<CapturedClass[] | null>(null) // AI가 읽은 수업. 있으면 확인 시트를 연다
  const fileRef = useRef<HTMLInputElement>(null)

  const classCount = new Set(blocks.filter((b) => b.source === 'everytime').map((b) => b.title)).size
  const googleCount = blocks.filter((b) => b.source === 'google').length

  const showLoaded = ({ count, term, termState }: LinkResult) => {
    setEt({ state: 'ok', message: `${term ? `${term} ` : ''}수업 ${count}개를 가져왔어요` })
    if (termState === 'past') setEtNote('past')
    else setEtOpen(false)
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
  const googleOn = googleCount > 0 || gc.state === 'ok' // 이번 주에 약속이 없어도 방금 연결했으면 켜짐

  return (
    <>
      <div className={styles.row}>
        <div>
          <p className="strong">에브리타임 시간표</p>
          <p className="meta">{classCount > 0 ? `수업 ${classCount}개 · 다시 넣으면 새로 바뀌어요` : '매주 반복되는 수업'}</p>
        </div>
        {classCount > 0 && !etOpen ? (
          <button type="button" className={`link ${styles.again}`} onClick={() => setEtOpen(true)}>
            다시 불러오기
          </button>
        ) : (
          !etOpen && (
            <button type="button" className="btn small" onClick={() => setEtOpen(true)}>
              불러오기
            </button>
          )
        )}
        {etOpen && (
          <div className={styles.full}>
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
            <div className={styles.subActions}>
              <button type="button" className="link" disabled={et.state === 'reading'} onClick={() => fileRef.current?.click()}>
                캡처로 올리기
              </button>
              <button type="button" className="link quiet" onClick={() => setEtOpen(false)}>
                닫기
              </button>
            </div>
          </div>
        )}
        <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={readCapture} />
        {(et.state !== 'idle' || etNote) && (
          <div className={styles.full}>
            {et.state === 'reading' && <p className={`meta ${styles.msg}`}>시간표를 읽는 중이에요…</p>}
            {(et.state === 'ok' || et.state === 'fail') && (
              <p className={`${styles.msg} ${et.state === 'fail' ? styles.bad : ''}`} role={et.state === 'fail' ? 'alert' : 'status'}>
                {et.message}
              </p>
            )}
            {etNote === 'past' && (
              <p className={`${styles.msg} ${styles.warn}`} role="alert">
                지난 학기 시간표예요. 이번 학기 시간표 링크를 넣어 주세요.
              </p>
            )}
            {etNote === 'manual' && (
              <button type="button" className={`link ${styles.msg}`} onClick={() => onAdd('weekly')}>
                수업 직접 넣기
              </button>
            )}
          </div>
        )}
      </div>

      <div className={styles.row}>
        <div>
          <p className="strong">구글 캘린더</p>
          <p className="meta">그날만 있는 약속</p>
          {gc.state === 'reading' && <p className={`meta ${styles.msg}`}>구글 창에서 허락하면 약속을 읽어 와요…</p>}
          {(gc.state === 'ok' || gc.state === 'fail') && (
            <p className={`${styles.msg} ${gc.state === 'fail' ? styles.bad : ''}`} role={gc.state === 'fail' ? 'alert' : 'status'}>
              {gc.message}
            </p>
          )}
        </div>
        {googleOn ? (
          <Badge tone="ok">켜짐</Badge>
        ) : (
          <button type="button" className="btn small" disabled={gc.state === 'reading'} onClick={linkGoogle}>
            연결
          </button>
        )}
      </div>

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
          팀원에게는 <b>바쁨 / 비어 있음</b>만 보여요. 약속 이름은 아무도 못 봐요.
        </p>
      )}
    </>
  )
}
