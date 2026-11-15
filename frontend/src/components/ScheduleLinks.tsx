import dayjs from 'dayjs'
import { useState } from 'react'
import { messageOf } from '../api/client.ts'
import { connectEverytime, connectGoogle } from '../api/me.ts'
import { WEEKDAYS, type Recurrence, type WeekBlock } from '../types/me.ts'
import Badge from './Badge.tsx'
import styles from './ScheduleLinks.module.css'

type Props = {
  blocks: WeekBlock[] // 이번 주 내 시간표. 어디서 온 일정이 있는지로 연결 여부를 본다
  onAdd: (recurrence: Recurrence) => void // "직접 추가"를 누르면 그 묶음(매주 반복·한 번만)의 추가 시트를 연다
  showLock?: boolean // 바쁨/비어 있음 안내. My 탭은 묶음 제목 옆에 따로 두어 끈다
}

type Reading = { state: 'idle' } | { state: 'reading' } | { state: 'ok' | 'fail'; message: string }

const hourText = (h: number) => (Number.isInteger(h) ? `${h}` : `${Math.floor(h)}:30`)

// 내 일정 가져오기: 두 묶음 × [연동 / 직접 추가]
//   매주 반복 — 에브리타임 공유 링크(수업) · 직접 추가(알바처럼 매주 있는 일)
//   한 번만   — 구글 캘린더(약속) · 직접 추가(그날만 있는 일)
export default function ScheduleLinks({ blocks, onAdd, showLock = true }: Props) {
  const [url, setUrl] = useState('')
  const [et, setEt] = useState<Reading>({ state: 'idle' })
  const [googleError, setGoogleError] = useState<string | null>(null)

  const classCount = new Set(blocks.filter((b) => b.source === 'everytime').map((b) => b.title)).size
  const googleCount = blocks.filter((b) => b.source === 'google').length
  const weekly = blocks.filter((b) => b.source === 'manual' && b.recurrence === 'weekly')
  const once = blocks.filter((b) => b.source === 'manual' && b.recurrence === 'once')
  const weeklyText = [...new Set(weekly.map((b) => b.title))]
    .map((t) => `${t} · ${weekly.filter((b) => b.title === t).map((b) => `${WEEKDAYS[b.weekday]} ${hourText(b.startHour)}–${hourText(b.endHour)}시`).join(', ')}`)
    .join(' / ')
  const onceText = once.map((b) => `${b.title} · ${dayjs(b.date).format('M/D')} ${hourText(b.startHour)}–${hourText(b.endHour)}시`).join(' / ')

  const loadEverytime = async () => {
    setEt({ state: 'reading' })
    try {
      const { count } = await connectEverytime(url.trim())
      setEt({ state: 'ok', message: `수업 ${count}개를 가져왔어요` })
    } catch (e) {
      setEt({ state: 'fail', message: messageOf(e) })
    }
  }
  const linkGoogle = async () => {
    try {
      await connectGoogle() // 연결되면 가져온 약속 수가 위 설명 줄에 보인다
      setGoogleError(null)
    } catch (e) {
      setGoogleError(messageOf(e))
    }
  }

  return (
    <>
      <p className={styles.group}>매주 반복</p>
      <div className={styles.row}>
        <div>
          <p className="strong">
            에브리타임 시간표 {classCount > 0 && <Badge tone="ok">가져옴</Badge>}
          </p>
          <p className="meta">{classCount > 0 ? `수업 ${classCount}개 · 링크를 다시 넣으면 새로 불러와요` : '수업 · 시간표 공유 링크를 붙여 넣어요'}</p>
          <div className={styles.input}>
            <input
              className="field num"
              value={url}
              placeholder="everytime.kr/@아이디"
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
      <ManualRow text={weeklyText || '알바처럼 매주 있는 일'} onAdd={() => onAdd('weekly')} />

      <p className={styles.group}>한 번만</p>
      <div className={styles.row}>
        <div>
          <p className="strong">구글 캘린더</p>
          <p className="meta">{googleCount > 0 ? `약속 ${googleCount}개를 가져왔어요` : '약속 · 읽기 권한만 받아요'}</p>
          {googleError && (
            <p className={`${styles.msg} ${styles.bad}`} role="alert">
              {googleError}
            </p>
          )}
        </div>
        {googleCount > 0 ? (
          <Badge tone="ok">켜짐</Badge>
        ) : (
          <button type="button" className="btn small" onClick={linkGoogle}>
            연결
          </button>
        )}
      </div>
      <ManualRow text={onceText || '병원 예약처럼 그날만 있는 일'} onAdd={() => onAdd('once')} />

      {showLock && (
        <p className={styles.lock}>
          팀원에게는 <b>바쁨 / 비어 있음</b>만 보여요. 약속 이름은 아무도 못 봐요.
        </p>
      )}
    </>
  )
}

function ManualRow({ text, onAdd }: { text: string; onAdd: () => void }) {
  return (
    <div className={styles.row}>
      <div>
        <p className="strong">직접 추가</p>
        <p className="meta">{text}</p>
      </div>
      <button type="button" className="btn small" onClick={onAdd}>
        넣기
      </button>
    </div>
  )
}
