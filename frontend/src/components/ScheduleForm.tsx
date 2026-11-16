import dayjs from 'dayjs'
import { useState, type ReactNode } from 'react'
import { messageOf } from '../api/client.ts'
import { addScheduleItem } from '../api/me.ts'
import form from '../pages/Form.module.css'
import FieldError, { type FormProblem } from './FieldError.tsx'
import { WEEKDAYS, type Recurrence, type ScheduleItemInput } from '../types/me.ts'
import styles from './ScheduleForm.module.css'
import Segmented from './Segmented.tsx'
import seg from './Segmented.module.css'
import Sheet from './Sheet.tsx'

const KINDS = ['일정', '수업'] as const
const HOURS = Array.from({ length: 13 }, (_, i) => i + 9) // 9:00~21:00

type Props = {
  recurrence: Recurrence // 처음 열릴 때 고른 쪽. 시트 안에서 바꿀 수 있다
  onSaved: (message: string) => void
  onCancel: () => void
}

const MODES = ['한 번만', '매주 반복'] as const
const MODE_OF: Record<(typeof MODES)[number], Recurrence> = { '한 번만': 'once', '매주 반복': 'weekly' }

// 일정 직접 추가 시트 하나. 맨 위에서 한 번만 / 매주 반복을 고른다. '좋아하는 방식' 시트와 같은 모양.
//   한 번만: 이름 · 날짜 · 시간
//   매주 반복: 이름 · 종류 · 요일 여러 개 · 요일마다 시간
// 구글 캘린더 약속은 캘린더에서 고친다
export default function ScheduleForm({ recurrence, onSaved, onCancel }: Props) {
  const [mode, setMode] = useState<Recurrence>(recurrence)
  const switcher = (
    <Segmented
      label="반복"
      options={MODES}
      value={mode === 'once' ? '한 번만' : '매주 반복'}
      onChange={(m) => setMode(MODE_OF[m])}
    />
  )
  return mode === 'weekly' ? (
    <WeeklyForm switcher={switcher} onSaved={onSaved} onCancel={onCancel} />
  ) : (
    <OnceForm switcher={switcher} onSaved={onSaved} onCancel={onCancel} />
  )
}

type FormProps = Omit<Props, 'recurrence'> & { switcher: ReactNode }

function WeeklyForm({ switcher, onSaved, onCancel }: FormProps) {
  const [title, setTitle] = useState('')
  const [kind, setKind] = useState<(typeof KINDS)[number]>('일정')
  const [days, setDays] = useState<Record<number, [number, number]>>({ 0: [18, 20] })
  const [problem, setProblem] = useState<FormProblem>(null)
  const [saving, setSaving] = useState(false)
  const picked = Object.keys(days).map(Number).sort()

  const typeTitle = (value: string) => {
    setTitle(value)
    setProblem(null) // 쓰기 시작하면 "이름을 적어 주세요"를 걷는다
  }
  const toggleDay = (d: number) => {
    if (d in days) {
      if (picked.length === 1) return setProblem({ at: 'days', message: '요일을 하나는 골라야 해요.' })
      setDays(Object.fromEntries(Object.entries(days).filter(([k]) => Number(k) !== d)))
    } else {
      setDays({ ...days, [d]: days[picked.at(-1) ?? 0] ?? [18, 20] }) // 마지막 요일 시간을 그대로 가져온다
    }
    setProblem(null)
  }
  const setTime = (d: number, i: 0 | 1, h: number) => setDays({ ...days, [d]: i === 0 ? [h, days[d][1]] : [days[d][0], h] })

  const save = async () => {
    if (!title.trim()) return setProblem({ at: 'title', message: '이름을 적어 주세요.' })
    const bad = picked.find((d) => days[d][1] <= days[d][0])
    if (bad !== undefined) return setProblem({ at: 'time', message: `${WEEKDAYS[bad]}요일 끝나는 시간이 시작보다 늦어야 해요.` })
    const input: ScheduleItemInput = {
      recurrence: 'weekly',
      title: title.trim(),
      kind: kind === '수업' ? 'class' : 'event',
      days: picked.map((d) => ({ weekday: d, startHour: days[d][0], endHour: days[d][1] })),
    }
    setSaving(true)
    try {
      await addScheduleItem(input)
      onSaved(`매주 ${picked.map((d) => WEEKDAYS[d]).join('·')}요일에 넣었어요`)
    } catch (e) {
      setProblem({ at: 'end', message: messageOf(e) })
      setSaving(false)
    }
  }

  return (
    <Sheet title="일정 추가" onClose={onCancel} actions={<Actions saving={saving} onCancel={onCancel} onSave={save} />}>
      {switcher}
      <label className={form.label}>
        이름
        <input className="field" value={title} maxLength={20} placeholder="예: 카페 알바" onChange={(e) => typeTitle(e.target.value)} />
      </label>
      <FieldError problem={problem} at="title" />
      <span className={form.label}>종류</span>
      <Segmented label="종류" options={KINDS} value={kind} onChange={setKind} />
      <span className={form.label}>요일 (매주 반복 · 복수 선택)</span>
      <div className={`${seg.seg} ${styles.days}`} role="group" aria-label="요일">
        {WEEKDAYS.map((w, d) => (
          <button key={w} type="button" aria-pressed={d in days} onClick={() => toggleDay(d)}>
            {w}
          </button>
        ))}
      </div>
      <FieldError problem={problem} at="days" />
      <span className={form.label}>시간</span>
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
      <FieldError problem={problem} at="time" />
      <FieldError problem={problem} at="end" />
    </Sheet>
  )
}

// 한 번만: 날짜 하루와 시간. 지난 날짜는 고를 수 없다
function OnceForm({ switcher, onSaved, onCancel }: FormProps) {
  const today = dayjs().format('YYYY-MM-DD')
  const [title, setTitle] = useState('')
  const [date, setDate] = useState(today)
  const [time, setTime] = useState<[number, number]>([18, 20])
  const [problem, setProblem] = useState<FormProblem>(null)
  const [saving, setSaving] = useState(false)
  const typeTitle = (value: string) => {
    setTitle(value)
    setProblem(null)
  }

  const save = async () => {
    if (!title.trim()) return setProblem({ at: 'title', message: '이름을 적어 주세요.' })
    if (!date || date < today) return setProblem({ at: 'date', message: '오늘이나 그 뒤 날짜를 골라 주세요.' })
    if (time[1] <= time[0]) return setProblem({ at: 'time', message: '끝나는 시간이 시작보다 늦어야 해요.' })
    setSaving(true)
    try {
      await addScheduleItem({ recurrence: 'once', title: title.trim(), date, startHour: time[0], endHour: time[1] })
      onSaved(`${dayjs(date).format('M/D')} ${time[0]}–${time[1]}시에 넣었어요`)
    } catch (e) {
      setProblem({ at: 'end', message: messageOf(e) })
      setSaving(false)
    }
  }

  return (
    <Sheet title="일정 추가" onClose={onCancel} actions={<Actions saving={saving} onCancel={onCancel} onSave={save} />}>
      {switcher}
      <label className={form.label}>
        이름
        <input className="field" value={title} maxLength={20} placeholder="예: 동아리 MT" onChange={(e) => typeTitle(e.target.value)} />
      </label>
      <FieldError problem={problem} at="title" />
      <label className={form.label}>
        날짜
        <input className="field num" type="date" min={today} value={date} onChange={(e) => setDate(e.target.value)} />
      </label>
      <FieldError problem={problem} at="date" />
      <span className={form.label}>시간</span>
      <div className={form.range}>
        <HourSelect label="시작" value={time[0]} onChange={(h) => setTime([h, time[1]])} />
        <span>–</span>
        <HourSelect label="끝" value={time[1]} onChange={(h) => setTime([time[0], h])} />
      </div>
      <FieldError problem={problem} at="time" />
      <FieldError problem={problem} at="end" />
    </Sheet>
  )
}

function Actions({ saving, onCancel, onSave }: { saving: boolean; onCancel: () => void; onSave: () => void }) {
  return (
    <>
      <button type="button" className="btn quiet" onClick={onCancel}>
        취소
      </button>
      <button type="button" className="btn primary" disabled={saving} onClick={onSave}>
        {saving ? '저장하는 중…' : '저장'}
      </button>
    </>
  )
}

export function HourSelect({ label, value, onChange }: { label: string; value: number; onChange: (h: number) => void }) {
  return (
    <select className={`field num ${styles.hour}`} aria-label={label} value={value} onChange={(e) => onChange(Number(e.target.value))}>
      {HOURS.map((h) => (
        <option key={h} value={h}>
          {h}:00
        </option>
      ))}
    </select>
  )
}
