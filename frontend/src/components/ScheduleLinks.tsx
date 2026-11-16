import { useState, type ReactNode } from 'react'
import { messageOf } from '../api/client.ts'
import { connectEverytime, connectGoogle } from '../api/me.ts'
import type { Recurrence, WeekBlock } from '../types/me.ts'
import styles from './ScheduleLinks.module.css'

type Props = {
  blocks: WeekBlock[] // 이번 주 내 시간표. 어디서 온 일정이 있는지로 연결 여부를 본다
  onAdd: (recurrence: Recurrence) => void // "일정 직접 추가"를 누르면 추가 시트를 연다(시트 안에서 한 번만·매주 반복을 고른다)
  showLock?: boolean // 바쁨/비어 있음 안내. My 탭에서는 끈다
}

type Reading = { state: 'idle' } | { state: 'reading' } | { state: 'ok' | 'fail'; message: string }

// 내 일정 넣기: 설정 목록처럼 줄 전체를 누른다 — 이름 | 오른쪽 상태 글자 + ›
//   에브리타임 시간표: 누르면 그 아래에 링크 칸이 열린다
//   구글 캘린더: 누르면 구글 연결 팝업. 연결되면 "연결됨"
//   일정 직접 추가: 누르면 시트(한 번만 / 매주 반복)
// 성공·실패 문구는 그 줄 아래 한 줄로 보인다
export default function ScheduleLinks({ blocks, onAdd, showLock = true }: Props) {
  const [url, setUrl] = useState('')
  const [etOpen, setEtOpen] = useState(false)
  const [et, setEt] = useState<Reading>({ state: 'idle' })
  const [gc, setGc] = useState<Reading>({ state: 'idle' })

  const classCount = new Set(blocks.filter((b) => b.source === 'everytime').map((b) => b.title)).size
  const googleCount = blocks.filter((b) => b.source === 'google').length

  const loadEverytime = async () => {
    setEt({ state: 'reading' })
    try {
      const { count, term } = await connectEverytime(url.trim())
      setEt({ state: 'ok', message: `${term ? `${term} ` : ''}수업 ${count}개를 가져왔어요` })
      setEtOpen(false)
      setUrl('')
    } catch (e) {
      setEt({ state: 'fail', message: messageOf(e) })
    }
  }
  // 구글 팝업은 클릭 직후에 열려야 막히지 않는다. connectGoogle을 다른 await보다 먼저 부른다
  const linkGoogle = async () => {
    setGc({ state: 'reading' })
    try {
      const { count } = await connectGoogle()
      setGc({ state: 'ok', message: `팀플 마감까지 약속 ${count}개를 가져왔어요` })
    } catch (e) {
      setGc({ state: 'fail', message: messageOf(e) })
    }
  }
  const googleOn = googleCount > 0 || gc.state === 'ok' // 이번 주에 약속이 없어도 방금 연결했으면 켜짐

  return (
    <>
      <ul className={styles.list}>
        <Row
          title="에브리타임 시간표"
          value={et.state === 'reading' ? '읽는 중…' : classCount > 0 ? `수업 ${classCount}개` : '가져오기'}
          on={classCount > 0}
          expanded={etOpen}
          onPress={() => setEtOpen(!etOpen)}
          note={note(et)}
        >
          {etOpen && (
            <div className={styles.input}>
              <input
                className="field num"
                value={url}
                placeholder="에타 시간표 → 공유 → 링크 복사"
                aria-label="에브리타임 공유 링크"
                autoFocus
                onChange={(e) => setUrl(e.target.value)}
              />
              <button type="button" className="btn small primary" disabled={!url.trim() || et.state === 'reading'} onClick={loadEverytime}>
                불러오기
              </button>
            </div>
          )}
        </Row>

        <Row
          title="구글 캘린더"
          value={gc.state === 'reading' ? '연결 중…' : googleOn ? '연결됨' : '연결 안 됨'}
          on={googleOn}
          onPress={googleOn || gc.state === 'reading' ? undefined : linkGoogle}
          note={note(gc)}
        />

        <Row title="일정 직접 추가" value={null} mark="+" onPress={() => onAdd('once')} />
      </ul>

      {showLock && (
        <p className={styles.lock}>
          팀원에게는 <b>바쁨 / 비어 있음</b>만 보여요. 약속 이름은 나만 봐요.
        </p>
      )}
    </>
  )
}

// 줄 아래 한 줄: 방금 성공·실패한 문구
function note(r: Reading): ReactNode {
  if (r.state === 'fail')
    return (
      <span className={styles.bad} role="alert">
        {r.message}
      </span>
    )
  if (r.state === 'ok') return <span role="status">{r.message}</span>
  return null
}

type RowProps = {
  title: string
  value: string | null // 오른쪽 상태 글자
  on?: boolean // 연결돼 있으면 상태 글자를 포인트색으로
  mark?: string // 오른쪽 끝 표시. 기본 ›
  expanded?: boolean
  onPress?: () => void // 없으면 누를 수 없는 줄(이미 연결됨)
  note?: ReactNode
  children?: ReactNode
}

function Row({ title, value, on = false, mark = '›', expanded, onPress, note, children }: RowProps) {
  const inner = (
    <>
      <span className="strong">{title}</span>
      {value && <span className={`${styles.value} ${on ? styles.on : ''}`}>{value}</span>}
      {onPress && (
        <span className={styles.mark} aria-hidden="true">
          {mark}
        </span>
      )}
    </>
  )
  return (
    <li className={styles.item}>
      {onPress ? (
        <button type="button" className={styles.row} aria-expanded={expanded} onClick={onPress}>
          {inner}
        </button>
      ) : (
        <div className={styles.row}>{inner}</div>
      )}
      {note && <p className={styles.note}>{note}</p>}
      {children && <div className={styles.full}>{children}</div>}
    </li>
  )
}
