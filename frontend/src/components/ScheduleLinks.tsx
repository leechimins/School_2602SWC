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

// 내 일정 가져오기: 두 묶음 × 두 방식 [연동 / 직접 추가]. 묶음 제목이 카드 제목을 대신하고,
// 연동이 먼저라 연동은 줄로, 직접 추가는 제목 오른쪽 작은 링크로 둔다
//   반복 일정(매주)   — 에브리타임 공유 링크 또는 시간표 캡처(수업) / 직접 추가(알바처럼 매주 있는 일)
//   일회성 일정(그날) — 구글 캘린더(약속)         / 직접 추가(그날만 있는 일)
// 아직 아무것도 없으면 설명 문구 없이 제목과 버튼만 보인다
export default function ScheduleLinks({ blocks, onAdd, showLock = true }: Props) {
  const [url, setUrl] = useState('')
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
      <GroupHead title="반복 일정" onAdd={() => onAdd('weekly')} />
      {/* 다른 줄처럼 이름 | 오른쪽 뱃지, 링크 칸은 그 아래 한 줄 전체 */}
      <div className={styles.row}>
        <div>
          <p className="strong">에브리타임 시간표</p>
          {classCount > 0 && <p className="meta">수업 {classCount}개 · 다시 넣으면 새로 바뀌어요</p>}
        </div>
        {classCount > 0 && <Badge tone="ok">가져옴</Badge>}
        <div className={styles.full}>
          <div className={styles.input}>
            <input
              className="field num"
              value={url}
              placeholder="에타 시간표 → 공유 → 링크 복사"
              aria-label="에브리타임 공유 링크"
              onChange={(e) => setUrl(e.target.value)}
            />
            <button type="button" className="btn small" disabled={!url.trim() || et.state === 'reading'} onClick={loadEverytime}>
              불러오기
            </button>
          </div>
          <button
            type="button"
            className={`link ${styles.capture}`}
            disabled={et.state === 'reading'}
            onClick={() => fileRef.current?.click()}
          >
            캡처로 올리기
          </button>
          <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={readCapture} />
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
      </div>

      <GroupHead title="일회성 일정" onAdd={() => onAdd('once')} />
      <div className={styles.row}>
        <div>
          <p className="strong">구글 캘린더</p>
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

// 묶음 제목(카드 제목 크기) | 오른쪽 "직접 추가". 연동이 먼저고 직접 추가는 보조라 제목 옆 작은 링크로 둔다.
// 넣은 일정은 위 시간표에 보이므로 여기 다시 늘어놓지 않는다
function GroupHead({ title, onAdd }: { title: string; onAdd: () => void }) {
  return (
    <div className={`row-between ${styles.group}`}>
      <h2>{title}</h2>
      <button type="button" className="link" onClick={onAdd}>
        직접 추가
      </button>
    </div>
  )
}
