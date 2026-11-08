import { useState } from 'react'
import { messageOf } from '../api/client.ts'
import { addScheduleItem } from '../api/me.ts'
import form from '../pages/Form.module.css'
import { WEEKDAYS, type ScheduleItemInput } from '../types/me.ts'
import styles from './ScheduleForm.module.css'
import Segmented from './Segmented.tsx'
import seg from './Segmented.module.css'

const KINDS = ['일정', '수업'] as const
const HOURS = Array.from({ length: 13 }, (_, i) => i + 9) // 9:00~21:00

type Props = {
  onSaved: (message: string) => void
  onCancel: () => void
}

// 일정 추가(매주 반복): 이름 · 종류 · 요일 여러 개 · 요일마다 시간. 구글 캘린더 약속은 캘린더에서 고친다
export default function ScheduleForm({ onSaved, onCancel }: Props) {
  const [title, setTitle] = useState('')
  const [kind, setKind] = useState<(typeof KINDS)[number]>('일정')
  const [days, setDays] = useState<Record<number, [number, number]>>({ 0: [18, 20] })
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const picked = Object.keys(days).map(Number).sort()

  const toggleDay = (d: number) => {
    if (d in days) {
      if (picked.length === 1) return setError('요일을 하나는 골라야 해요.')
      setDays(Object.fromEntries(Object.entries(days).filter(([k]) => Number(k) !== d)))
    } else {
      setDays({ ...days, [d]: days[picked.at(-1) ?? 0] ?? [18, 20] }) // 마지막 요일 시간을 그대로 가져온다
    }
    setError(null)
  }
  const setTime = (d: number, i: 0 | 1, h: number) => setDays({ ...days, [d]: i === 0 ? [h, days[d][1]] : [days[d][0], h] })

  const save = async () => {
    const bad = picked.find((d) => days[d][1] <= days[d][0])
    if (bad !== undefined) return setError(`${WEEKDAYS[bad]}요일 끝나는 시간이 시작보다 늦어야 해요.`)
    const input: ScheduleItemInput = {
      title: title.trim() || kind,
      kind: kind === '수업' ? 'class' : 'event',
      days: picked.map((d) => ({ weekday: d, startHour: days[d][0], endHour: days[d][1] })),
    }
    setSaving(true)
    try {
      await addScheduleItem(input)
      onSaved(`매주 ${picked.map((d) => WEEKDAYS[d]).join('·')}요일에 넣었어요. 에이전트가 이 시간은 빼고 조율해요.`)
    } catch (e) {
      setError(messageOf(e))
      setSaving(false)
    }
  }

  return (
    <div className={styles.box}>
      <p className="strong">일정 추가</p>
      <label className={form.label}>
        이름 (나만 보여요)
        <input className="field" value={title} maxLength={20} placeholder="예: 카페 알바" onChange={(e) => setTitle(e.target.value)} />
      </label>
      <span className={form.label}>종류</span>
      <Segmented label="종류" options={KINDS} value={kind} onChange={setKind} />
      <span className={form.label}>요일 (매주 반복 · 여러 개 고를 수 있어요)</span>
      <div className={`${seg.seg} ${styles.days}`} role="group" aria-label="요일">
        {WEEKDAYS.map((w, d) => (
          <button key={w} type="button" aria-pressed={d in days} onClick={() => toggleDay(d)}>
            {w}
          </button>
        ))}
      </div>
      <span className={form.label}>시간 (요일마다 달라도 돼요)</span>
      {picked.map((d) => (
        <div key={d} className={styles.dayTime}>
          <b>{WEEKDAYS[d]}</b>
          <div className={form.range}>
            <HourSelect label={`${WEEKDAYS[d]} 시작`} value={days[d][0]} onChange={(h) => setTime(d, 0, h)} />
            <span>–</span>
            <HourSelect label={`${WEEKDAYS[d]} 끝`} value={days[d][1]} onChange={(h) => setTime(d, 1, h)} />
          </div>
        </div>
      ))}
      {error && (
        <p className={form.error} role="alert">
          {error}
        </p>
      )}
      <div className={styles.act}>
        <button type="button" className="btn small quiet" onClick={onCancel}>
          취소
        </button>
        <button type="button" className="btn small primary" disabled={saving} onClick={save}>
          저장
        </button>
      </div>
    </div>
  )
}

export function HourSelect({ label, value, onChange }: { label: string; value: number; onChange: (h: number) => void }) {
  return (
    <select className="field num" aria-label={label} value={value} onChange={(e) => onChange(Number(e.target.value))}>
      {HOURS.map((h) => (
        <option key={h} value={h}>
          {h}:00
        </option>
      ))}
    </select>
  )
}
