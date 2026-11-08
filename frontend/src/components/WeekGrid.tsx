import { useRef, type KeyboardEvent, type MouseEvent } from 'react'
import { WEEKDAYS, type WeekBlock } from '../types/me.ts'
import styles from './WeekGrid.module.css'

const FROM = 9 // 9시~21시만 그린다. 밖으로 나간 칸은 끝에 붙인다
const TO = 21
const pct = (h: number) => `${((Math.min(Math.max(h, FROM), TO) - FROM) / (TO - FROM)) * 100}%`
const HOLD_MS = 500 // 이만큼 누르고 있으면 고치기

/** 길게 눌러 고칠 수 있는 칸: 직접 넣은 일정만. 수업·구글 약속은 가져온 곳에서 고친다 */
const isEditable = (b: WeekBlock) => b.source === 'manual' && b.itemId !== null

/** 칸 색 종류: 일정은 어디서 왔는지(구글·직접)로 나눈다. 직접 넣은 칸만 고칠 수 있어서 눈에 구분되게 */
type Look = 'class' | 'google' | 'manual' | 'meeting' | 'waiting'
const lookOf = (b: WeekBlock): Look => (b.kind === 'event' ? (b.source === 'google' ? 'google' : 'manual') : b.kind)

const LEGEND: [Look, string][] = [
  ['class', '수업'],
  ['google', '일정(구글)'],
  ['manual', '일정(직접)'],
  ['meeting', '팀 회의'],
  ['waiting', '확정 대기'],
]

type Props = {
  blocks: WeekBlock[]
  onEdit?: (block: WeekBlock) => void // 주면 직접 넣은 일정을 길게 눌러(키보드는 Enter) 고칠 수 있다
}

// 내 한 주 시간표: 수업 / 일정(구글·직접) / 팀 회의(확정 대기는 점선). 남에게는 바쁨·비어 있음만 보이고, 이 화면은 나만 본다
export default function WeekGrid({ blocks, onEdit }: Props) {
  const timer = useRef<number | undefined>(undefined)
  const cancel = () => window.clearTimeout(timer.current)
  // 편집할 수 있는 칸에만 길게 누르기를 붙인다
  const holdProps = (b: WeekBlock) =>
    onEdit && isEditable(b)
      ? {
          role: 'button',
          tabIndex: 0,
          'aria-label': `${b.title} 고치기`,
          'data-edit': true,
          onPointerDown: () => {
            cancel()
            timer.current = window.setTimeout(() => onEdit(b), HOLD_MS)
          },
          onPointerUp: cancel,
          onPointerLeave: cancel,
          onPointerCancel: cancel,
          onContextMenu: (e: MouseEvent) => e.preventDefault(), // 휴대폰 길게 누르기 메뉴 대신
          onKeyDown: (e: KeyboardEvent) => e.key === 'Enter' && onEdit(b),
        }
      : {}

  return (
    <>
      <div className={styles.week}>
        <span />
        {WEEKDAYS.map((w) => (
          <span key={w} className={styles.wd}>
            {w}
          </span>
        ))}
        <div className={styles.hours} aria-hidden="true">
          {[9, 12, 15, 18, 21].map((h) => (
            <span key={h} style={{ top: pct(h) }} className="num">
              {h}
            </span>
          ))}
        </div>
        {WEEKDAYS.map((w, d) => (
          <div key={w} className={styles.col}>
            {blocks
              .filter((b) => b.weekday === d && b.endHour > FROM && b.startHour < TO)
              .map((b, i) => (
                <span
                  key={i}
                  className={styles.blk}
                  data-k={lookOf(b)}
                  style={{ top: pct(b.startHour), height: `calc(${pct(b.endHour)} - ${pct(b.startHour)})` }}
                  title={`${w} ${b.startHour}–${b.endHour}시 ${b.title}`}
                  {...holdProps(b)}
                >
                  {b.title}
                </span>
              ))}
          </div>
        ))}
      </div>
      <div className={styles.legend}>
        {LEGEND.map(([k, label]) => (
          <span key={k}>
            <i data-k={k} />
            {label}
          </span>
        ))}
      </div>
    </>
  )
}
