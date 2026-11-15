import { useState } from 'react'
import { messageOf } from '../api/client.ts'
import { connectEverytime, connectGoogle } from '../api/me.ts'
import type { Recurrence, WeekBlock } from '../types/me.ts'
import Badge from './Badge.tsx'
import styles from './ScheduleLinks.module.css'

type Props = {
  blocks: WeekBlock[] // 이번 주 내 시간표. 어디서 온 일정이 있는지로 연결 여부를 본다
  onAdd: (recurrence: Recurrence) => void // "직접 추가"를 누르면 그 묶음(매주 반복·한 번만)의 추가 시트를 연다
  showLock?: boolean // 바쁨/비어 있음 안내. My 탭에서는 끈다
}

type Reading = { state: 'idle' } | { state: 'reading' } | { state: 'ok' | 'fail'; message: string }

// 내 일정 가져오기: 두 묶음 × 두 방식 [연동 / 직접 추가]. 두 방식은 같은 모양의 줄로 나란히 보인다
//   반복 일정(매주)   — 에브리타임 공유 링크(수업) / 직접 추가(알바처럼 매주 있는 일)
//   일회성 일정(그날) — 구글 캘린더(약속)         / 직접 추가(그날만 있는 일)
// 아직 아무것도 없으면 설명 문구 없이 제목과 버튼만 보인다
export default function ScheduleLinks({ blocks, onAdd, showLock = true }: Props) {
  const [url, setUrl] = useState('')
  const [et, setEt] = useState<Reading>({ state: 'idle' })
  const [gc, setGc] = useState<Reading>({ state: 'idle' })

  const classCount = new Set(blocks.filter((b) => b.source === 'everytime').map((b) => b.title)).size
  const googleCount = blocks.filter((b) => b.source === 'google').length

  const loadEverytime = async () => {
    setEt({ state: 'reading' })
    try {
      const { count, term } = await connectEverytime(url.trim())
      setEt({ state: 'ok', message: `${term ? `${term} ` : ''}수업 ${count}개를 가져왔어요` })
    } catch (e) {
      setEt({ state: 'fail', message: messageOf(e) })
    }
  }
  // 구글 팝업은 클릭 직후에 열려야 막히지 않는다. connectGoogle을 다른 await보다 먼저 부른다
  const linkGoogle = async () => {
    setGc({ state: 'reading' })
    try {
      const { count } = await connectGoogle()
      setGc({ state: 'ok', message: `앞으로 5주 약속 ${count}개를 바쁨으로 넣었어요` })
    } catch (e) {
      setGc({ state: 'fail', message: messageOf(e) })
    }
  }
  const googleOn = googleCount > 0 || gc.state === 'ok' // 이번 주에 약속이 없어도 방금 연결했으면 켜짐

  return (
    <>
      <p className={styles.group}>반복 일정</p>
      {/* 다른 줄처럼 이름 | 오른쪽 뱃지, 링크 칸은 그 아래 한 줄 전체 */}
      <div className={styles.row}>
        <div>
          <p className="strong">에브리타임 시간표</p>
          {classCount > 0 && <p className="meta">수업 {classCount}개 · 링크를 다시 넣으면 새로 불러와요</p>}
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
          {et.state === 'reading' && <p className={`meta ${styles.msg}`}>시간표를 읽는 중이에요…</p>}
          {(et.state === 'ok' || et.state === 'fail') && (
            <p className={`${styles.msg} ${et.state === 'fail' ? styles.bad : ''}`} role={et.state === 'fail' ? 'alert' : 'status'}>
              {et.message}
            </p>
          )}
        </div>
      </div>
      <ManualRow what="에타에 없는 매주 일정" onAdd={() => onAdd('weekly')} />

      <p className={styles.group}>일회성 일정</p>
      <div className={styles.row}>
        <div>
          <p className="strong">구글 캘린더</p>
          {googleCount > 0 && <p className="meta">이번 주 약속 {googleCount}개 · 이름 없이 바쁨으로만</p>}
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
      <ManualRow what="캘린더에 없는 약속" onAdd={() => onAdd('once')} />

      {showLock && (
        <p className={styles.lock}>
          팀원에게는 <b>바쁨 / 비어 있음</b>만 보여요. 약속 이름은 아무도 못 봐요.
        </p>
      )}
    </>
  )
}

// 직접 추가: 연동이 먼저고 이것은 보조라, 연동 줄 아래 들여 쓴 작은 한 줄로 딸려 보인다.
// 넣은 일정은 위 시간표에 보이므로 여기 다시 늘어놓지 않는다
function ManualRow({ what, onAdd }: { what: string; onAdd: () => void }) {
  return (
    <p className={`meta ${styles.manual}`}>
      {what}은{' '}
      <button type="button" className="link" onClick={onAdd}>
        직접 추가
      </button>
    </p>
  )
}
