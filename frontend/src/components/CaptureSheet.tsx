import { useState } from 'react'
import { messageOf } from '../api/client.ts'
import { saveEverytimeCapture } from '../api/me.ts'
import form from '../pages/Form.module.css'
import { WEEKDAYS, type CapturedClass, type LinkResult } from '../types/me.ts'
import AiMark from './AiMark.tsx'
import styles from './CaptureSheet.module.css'
import Sheet from './Sheet.tsx'

type Props = {
  classes: CapturedClass[] // AI가 캡처에서 읽은 수업(아직 저장 전)
  onClose: () => void
  onSaved: (result: LinkResult) => void
}

// 시간표 캡처 확인·수정(#66). AI가 읽은 수업은 바로 저장하지 않고, 여기서 고친 뒤 "넣기"를 눌러야 일정에 들어간다.
// 한 수업 = 과목명 | 지우기 / 요일 · 시작 – 끝. 아래 버튼: 취소 | 수업 N개 넣기
export default function CaptureSheet({ classes, onClose, onSaved }: Props) {
  const [rows, setRows] = useState(classes)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const change = (i: number, patch: Partial<CapturedClass>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  const remove = (i: number) => setRows(rows.filter((_, j) => j !== i))
  const add = () => setRows([...rows, { title: '', weekday: 0, start: '09:00', end: '10:30' }])
  const invalid = (r: CapturedClass) => !r.title.trim() || !r.start || !r.end || r.start >= r.end // 'HH:mm'은 글자 비교로 순서가 맞다

  const save = async () => {
    if (rows.some(invalid)) return setError('과목명을 채우고, 끝나는 시간을 시작보다 늦게 맞춰 주세요.')
    setSaving(true)
    setError(null)
    try {
      onSaved(await saveEverytimeCapture(rows))
    } catch (e) {
      setError(messageOf(e))
      setSaving(false)
    }
  }

  return (
    <Sheet
      title="읽은 수업 확인"
      onClose={onClose}
      actions={
        <>
          <button type="button" className="btn quiet" onClick={onClose}>
            취소
          </button>
          <button type="button" className="btn primary" disabled={saving || rows.length === 0} onClick={save}>
            {saving ? '넣는 중…' : `수업 ${rows.length}개 넣기`}
          </button>
        </>
      }
    >
      <p className={`meta ${styles.hint}`}>
        <AiMark label="AI가 읽음" /> 틀린 칸은 고쳐 주세요. 넣기 전에는 일정에 들어가지 않아요.
      </p>
      <ul className={styles.list}>
        {rows.map((r, i) => (
          <li key={i} className={styles.item} aria-invalid={error ? invalid(r) : undefined}>
            <div className={styles.line}>
              <input
                className="field"
                value={r.title}
                maxLength={30}
                placeholder="과목명"
                aria-label={`${i + 1}번째 수업 과목명`}
                onChange={(e) => change(i, { title: e.target.value })}
              />
              <button type="button" className="btn del small" onClick={() => remove(i)} aria-label={`${r.title || `${i + 1}번째 수업`} 지우기`}>
                지우기
              </button>
            </div>
            <div className={form.range}>
              <select
                className={`field ${styles.day}`}
                value={r.weekday}
                aria-label="요일"
                onChange={(e) => change(i, { weekday: Number(e.target.value) })}
              >
                {WEEKDAYS.map((d, w) => (
                  <option key={d} value={w}>
                    {d}
                  </option>
                ))}
              </select>
              <input className="field num" type="time" step={300} value={r.start} aria-label="시작" onChange={(e) => change(i, { start: e.target.value })} />
              <span>–</span>
              <input className="field num" type="time" step={300} value={r.end} aria-label="끝" onChange={(e) => change(i, { end: e.target.value })} />
            </div>
          </li>
        ))}
      </ul>
      <button type="button" className="link" onClick={add}>
        수업 더하기
      </button>
      {error && (
        <p className={form.error} role="alert">
          {error}
        </p>
      )}
    </Sheet>
  )
}
