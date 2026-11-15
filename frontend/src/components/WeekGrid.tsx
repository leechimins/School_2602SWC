import type { CSSProperties, KeyboardEvent } from 'react'
import { showNotice } from '../lib/notice.ts'
import { WEEKDAYS, type WeekBlock } from '../types/me.ts'
import styles from './WeekGrid.module.css'

const HOUR_PX = 16 // 한 시간 높이. 한 시간짜리 칸에도 글자 한 줄이 들어간다
const LINKED_NOTICE = '연동된 일정은 여기서 바꿀 수 없어요. 에브리타임·구글 캘린더에서 고쳐 주세요.'

/** 눌러서 고칠 수 있는 칸: 직접 넣은 일정만. 수업·구글 약속은 가져온 곳에서 고친다 */
const isEditable = (b: WeekBlock) => b.source === 'manual' && b.itemId !== null
const isLinked = (b: WeekBlock) => b.source === 'everytime' || b.source === 'google'

/** 그릴 시간 범위: 기본 9~21시, 그 밖에 걸친 칸이 있으면 그만큼 넓힌다(0~24시 안) */
function rangeOf(blocks: WeekBlock[]): [number, number] {
  const from = Math.max(0, Math.min(9, ...blocks.map((b) => Math.floor(b.startHour))))
  const to = Math.min(24, Math.max(21, ...blocks.map((b) => Math.ceil(b.endHour))))
  return [from, to]
}

/** 칸 색 종류: 일정은 어디서 왔는지(구글·직접)로 나눈다. 직접 넣은 칸만 고칠 수 있어서 눈에 구분되게 */
type Look = 'class' | 'google' | 'manual' | 'meeting' | 'waiting'
const lookOf = (b: WeekBlock): Look => (b.kind === 'event' ? (b.source === 'google' ? 'google' : 'manual') : b.kind)

const LEGEND: [Look, string][] = [
  ['class', '수업'],
  ['google', '캘린더'],
  ['manual', '직접 추가'],
  ['meeting', '팀 회의'],
  ['waiting', '회의 대기'],
]

type Props = {
  blocks: WeekBlock[]
  onEdit?: (block: WeekBlock) => void // 주면 직접 넣은 일정을 눌러(키보드는 Enter) 고칠 수 있다
}

// 내 한 주 시간표: 수업 / 일정(구글·직접) / 팀 회의(확정 대기는 점선). 남에게는 바쁨·비어 있음만 보이고, 이 화면은 나만 본다
export default function WeekGrid({ blocks, onEdit }: Props) {
  const [from, to] = rangeOf(blocks)
  const pct = (h: number) => `${((Math.min(Math.max(h, from), to) - from) / (to - from)) * 100}%`
  const marks = Array.from({ length: Math.floor((to - from) / 3) + 1 }, (_, i) => from + i * 3)

  // 직접 넣은 칸은 누르면 고치기, 연동된 칸(수업·구글)은 누르면 못 고친다는 안내
  const press = (b: WeekBlock) => (onEdit && isEditable(b) ? () => onEdit(b) : onEdit && isLinked(b) ? () => showNotice(LINKED_NOTICE) : null)
  const editProps = (b: WeekBlock) => {
    const run = press(b)
    if (!run) return {}
    return {
      role: 'button',
      tabIndex: 0,
      'aria-label': isEditable(b) ? `${b.title} 고치기` : `${b.title} (연동된 일정)`,
      'data-edit': true,
      onClick: run,
      onKeyDown: (e: KeyboardEvent) => e.key === 'Enter' && run(),
    }
  }

  return (
    <>
      <div className={styles.week} style={{ '--grid-h': `${(to - from) * HOUR_PX}px` } as CSSProperties}>
        <span />
        {WEEKDAYS.map((w) => (
          <span key={w} className={styles.wd}>
            {w}
          </span>
        ))}
        <div className={styles.hours} aria-hidden="true">
          {marks.map((h) => (
            <span key={h} style={{ top: pct(h) }} className="num">
              {h}
            </span>
          ))}
        </div>
        {WEEKDAYS.map((w, d) => (
          <div key={w} className={styles.col}>
            {blocks
              .filter((b) => b.weekday === d && b.endHour > from && b.startHour < to)
              .map((b, i) => (
                <span
                  key={i}
                  className={styles.blk}
                  data-k={lookOf(b)}
                  data-short={b.endHour - b.startHour < 1 || undefined}
                  style={{ top: pct(b.startHour), height: `calc(${pct(b.endHour)} - ${pct(b.startHour)})` }}
                  title={`${w} ${b.startHour}–${b.endHour}시 ${b.title}`}
                  {...editProps(b)}
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
