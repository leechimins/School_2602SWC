import { DAYPARTS, PREF_MODES, type Daypart, type Preferences } from '../types/me.ts'
import form from '../pages/Form.module.css'
import styles from './PrefForm.module.css'
import Segmented from './Segmented.tsx'
import seg from './Segmented.module.css'

type Props = {
  value: Preferences
  onChange: (next: Preferences) => void
}

const HOURS = Array.from({ length: 15 }, (_, i) => i + 8) // 8시~22시

// 회의 잡을 때 쓸 조건 네 가지(온보딩 · 나 화면 공통). 세 가지는 고르기, 피하고 싶은 시간만 한 줄로 쓴다. 필수는 없다
export default function PrefForm({ value, onChange }: Props) {
  const set = <K extends keyof Preferences>(key: K, v: Preferences[K]) => onChange({ ...value, [key]: v })
  const toggleDaypart = (d: Daypart) =>
    set('dayparts', DAYPARTS.filter((o) => (o === d ? !value.dayparts.includes(d) : value.dayparts.includes(o))))

  return (
    <>
      <div className={styles.pref}>
        <span className="meta">몇 시부터 몇 시까지 회의할 수 있어요?</span>
        <div className={form.range}>
          <HourSelect label="몇 시부터" value={value.fromHour} onChange={(h) => set('fromHour', h)} />
          <span>–</span>
          <HourSelect label="몇 시까지" value={value.toHour} onChange={(h) => set('toHour', h)} />
        </div>
      </div>
      <div className={styles.pref}>
        <span className="meta">어떻게 만날까요?</span>
        <Segmented label="만나는 방식" options={PREF_MODES} value={value.mode ?? '상관없음'} onChange={(m) => set('mode', m)} />
      </div>
      <div className={styles.pref}>
        <span className="meta">언제가 좋아요? (여러 개)</span>
        <div className={seg.seg} role="group" aria-label="좋은 때">
          {DAYPARTS.map((d) => (
            <button key={d} type="button" aria-pressed={value.dayparts.includes(d)} onClick={() => toggleDaypart(d)}>
              {d}
            </button>
          ))}
        </div>
      </div>
      <div className={styles.pref}>
        <label className="meta" htmlFor="pref-avoid">
          꼭 피하고 싶은 시간이 있어요? (안 써도 돼요)
        </label>
        <textarea
          id="pref-avoid"
          className={`field ${form.textarea} ${styles.avoid}`}
          rows={2}
          maxLength={80}
          value={value.avoid}
          placeholder="예: 화요일 오전, 목요일 오후는 알바라 어려워요"
          onChange={(e) => set('avoid', e.target.value)}
        />
        <p className="meta">에이전트가 다듬어서 조율 근거로 써요.</p>
      </div>
    </>
  )
}

function HourSelect({ label, value, onChange }: { label: string; value: number | null; onChange: (h: number | null) => void }) {
  return (
    <select
      className="field"
      aria-label={label}
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
    >
      <option value="">정하지 않음</option>
      {HOURS.map((h) => (
        <option key={h} value={h}>
          {h}시
        </option>
      ))}
    </select>
  )
}
