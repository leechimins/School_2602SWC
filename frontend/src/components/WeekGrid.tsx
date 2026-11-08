import { WEEKDAYS, type WeekBlock } from '../types/me.ts'
import styles from './WeekGrid.module.css'

const FROM = 9 // 9시~21시만 그린다. 밖으로 나간 칸은 끝에 붙인다
const TO = 21
const pct = (h: number) => `${((Math.min(Math.max(h, FROM), TO) - FROM) / (TO - FROM)) * 100}%`

// 내 한 주 시간표: 수업 / 일정(알바·약속) / 팀 회의(확정 대기는 점선). 남에게는 바쁨·비어 있음만 보이고, 이 화면은 나만 본다
export default function WeekGrid({ blocks }: { blocks: WeekBlock[] }) {
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
                  data-k={b.kind}
                  style={{ top: pct(b.startHour), height: `calc(${pct(b.endHour)} - ${pct(b.startHour)})` }}
                  title={`${w} ${b.startHour}–${b.endHour}시 ${b.title}`}
                >
                  {b.title}
                </span>
              ))}
          </div>
        ))}
      </div>
      <div className={styles.legend}>
        <span>
          <i data-k="class" />
          수업
        </span>
        <span>
          <i data-k="event" />
          일정
        </span>
        <span>
          <i data-k="meeting" />
          팀 회의
        </span>
        <span>
          <i data-k="waiting" />
          확정 대기
        </span>
      </div>
    </>
  )
}
