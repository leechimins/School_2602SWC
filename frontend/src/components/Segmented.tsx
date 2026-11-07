import styles from './Segmented.module.css'

type Props<T extends string | number> = {
  label: string // 읽어 주는 이름: "방식"
  options: readonly T[]
  value: T
  format?: (option: T) => string
  onChange: (value: T) => void
}

// 여러 개 중 하나 고르기 (방식, 팀원 수). 눌린 칸은 aria-pressed로 알린다
export default function Segmented<T extends string | number>({ label, options, value, format = String, onChange }: Props<T>) {
  return (
    <div className={styles.seg} role="group" aria-label={label}>
      {options.map((option) => (
        <button key={option} type="button" aria-pressed={option === value} onClick={() => onChange(option)}>
          {format(option)}
        </button>
      ))}
    </div>
  )
}
