import { useState } from 'react'
import { messageOf } from '../api/client.ts'
import { deleteScheduleItem, editScheduleItem } from '../api/me.ts'
import form from '../pages/Form.module.css'
import { WEEKDAYS, type WeekBlock } from '../types/me.ts'
import { HourSelect } from './ScheduleForm.tsx'
import styles from './ScheduleEditSheet.module.css'
import Sheet from './Sheet.tsx'

type Props = { block: WeekBlock; onClose: () => void }

// 직접 넣은 일정 한 칸(요일 하나) 고치기·지우기. My 탭 시간표에서 길게 눌러 연다. 아래 버튼: 취소 | 삭제 | 저장
export default function ScheduleEditSheet({ block, onClose }: Props) {
  const [title, setTitle] = useState(block.title)
  const [from, setFrom] = useState(Math.floor(block.startHour))
  const [to, setTo] = useState(Math.ceil(block.endHour))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async (write: () => Promise<void>) => {
    setSaving(true)
    setError(null)
    try {
      await write()
      onClose()
    } catch (e) {
      setError(messageOf(e))
      setSaving(false)
    }
  }
  const itemId = block.itemId ?? ''
  const save = () => {
    if (to <= from) return setError('끝나는 시간이 시작보다 늦어야 해요.')
    run(() => editScheduleItem(itemId, { title: title.trim() || block.title, startHour: from, endHour: to }))
  }

  return (
    <Sheet
      title={`매주 ${WEEKDAYS[block.weekday]}요일 일정`}
      onClose={onClose}
      actions={
        <>
          <button type="button" className="btn quiet" onClick={onClose}>
            취소
          </button>
          <button type="button" className={`btn quiet ${styles.delete}`} disabled={saving} onClick={() => run(() => deleteScheduleItem(itemId))}>
            삭제
          </button>
          <button type="button" className="btn primary" disabled={saving} onClick={save}>
            저장
          </button>
        </>
      }
    >
      {/* 이름 한 줄 + 시간 한 줄 */}
      <input className={`field ${styles.name}`} value={title} maxLength={20} aria-label="일정 이름 (나만 보여요)" onChange={(e) => setTitle(e.target.value)} />
      <div className={`${form.range} ${styles.time}`}>
        <HourSelect label="시작" value={from} onChange={setFrom} />
        <span>–</span>
        <HourSelect label="끝" value={to} onChange={setTo} />
      </div>
      {error && (
        <p className={form.error} role="alert">
          {error}
        </p>
      )}
    </Sheet>
  )
}
