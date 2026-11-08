import { useRef, useState, useSyncExternalStore, type RefObject } from 'react'
import { USE_MOCK } from '../api/client.ts'
import { moveClock, resetClock, useClock } from '../hooks/useClock.ts'
import { formatMD, formatSlot, formatTime, weekday } from '../lib/date.ts'
import { DEBUG_OFF, getDebug, setDebug, type DebugFlags } from '../lib/debug.ts'
import { PATHS, pathTo } from '../lib/paths.ts'
import { getState, markChanged, resetState, subscribe } from '../mock/store.ts'
import { USER } from '../mock/seed.ts'
import type { Id } from '../types/common.ts'
import styles from './DemoPage.module.css'

// 시연 화면(/demo): 휴대폰 화면 2개(서로 다른 팀원)와 시연 장치를 한 페이지에 띄운다.
// 장치는 앱 화면 안에 넣지 않고 바깥 패널에 모은다(web-design 규칙). 패널은 앱 토큰을 쓰지 않는 회색이다.
// 두 화면과 이 패널은 같은 출처라 목 저장소를 함께 쓰고, 한쪽이 바꾸면 BroadcastChannel로 서로 다시 읽는다.
//
// 휴대폰 화면 이동은 iframe을 새로 불러오지 않고 주소만 바꾼다(history + popstate).
// 새로 불러오면 그 화면이 걸어 둔 조율 재생 타이머가 끊기기 때문이다.

type Frame = RefObject<HTMLIFrameElement | null>

const SLOW_OPTIONS = [0, 1_000, 3_000]
// 보는 사람은 고정: 왼쪽은 팀장 지수, 오른쪽은 팀원 민지(시연 대본이 이 두 사람 기준이다)
const USERS: [Id, Id] = [USER.jisu, USER.minji]

/** 휴대폰 화면 하나를 path로 옮기고, 보는 사람(?user)도 함께 정한다 */
function go(frame: Frame, path: string, userId: Id) {
  const w = frame.current?.contentWindow
  if (!w) return
  w.history.pushState(null, '', `${path}?user=${userId}`)
  w.dispatchEvent(new PopStateEvent('popstate'))
}

export default function DemoPage() {
  const left = useRef<HTMLIFrameElement>(null)
  const right = useRef<HTMLIFrameElement>(null)
  const [debug, setDebugState] = useState<DebugFlags>(getDebug)
  const s = useSyncExternalStore(subscribe, getState)
  const now = useClock()

  // 가장 최근 조율과 그 결과 회의안. 장면 바로 가기가 늘 지금 데이터를 가리키게 한다
  const lastScheduling = s.schedulings[s.schedulings.length - 1]
  const lastProposalId = lastScheduling?.meetingId ?? s.proposals[s.proposals.length - 1]?.meetingId
  const scenes: { label: string; path: string }[] = [
    { label: '홈', path: PATHS.home },
    { label: '회의 잡기', path: PATHS.schedulingNew },
    ...(lastScheduling ? [{ label: '시간 정하는 과정', path: pathTo.scheduling(lastScheduling.id) }] : []),
    ...(lastProposalId ? [{ label: '조율 확인', path: pathTo.proposal(lastProposalId) }] : []),
    { label: '팀', path: PATHS.team },
    { label: '할 일', path: PATHS.tasks },
    { label: '일정', path: PATHS.schedule },
    { label: '알림', path: PATHS.notifications },
  ]

  const frames: [Frame, Frame] = [left, right]
  const goBoth = (path: string) => frames.forEach((f, i) => go(f, path, USERS[i]))


  // 새로고침 없이 몇 번을 눌러도 같은 처음 화면이 되게(목업 버그 ④):
  // 데이터·시연 시계·걸어 둔 타이머, 점검 스위치까지 모두 처음으로
  const reset = () => {
    resetState()
    setDebug(DEBUG_OFF)
    setDebugState(DEBUG_OFF)
    goBoth(PATHS.home)
  }

  const changeDebug = (patch: Partial<DebugFlags>) => {
    const next = { ...debug, ...patch }
    setDebug(next)
    setDebugState(next)
    markChanged() // 두 화면이 다시 불러와 스위치가 바로 보이게
  }

  const nameOf = (id: Id) => s.members.find((m) => m.id === id)?.name ?? id

  return (
    <main className={styles.page}>
      {[0, 1].map((i) => (
        <div key={i} className={styles.phone}>
          {/* src는 처음 한 번만. 이후 이동은 go()로 */}
          <iframe ref={frames[i]} src={`/?user=${USERS[i]}`} title={i === 0 ? '휴대폰 화면 1 (팀장 지수)' : '휴대폰 화면 2 (팀원 민지)'} />
        </div>
      ))}

      <aside className={styles.panel}>
        <section>
          <h2>시연 시계</h2>
          <p className={styles.clock}>
            {formatMD(now)}({weekday(now)}) {formatTime(now)}
          </p>
          <div className={styles.buttons}>
            <button type="button" onClick={() => moveClock(-24 * 60)}>−1일</button>
            <button type="button" onClick={() => moveClock(30)}>+30분</button>
            <button type="button" onClick={() => moveClock(60)}>+1시간</button>
            <button type="button" onClick={() => moveClock(24 * 60)}>+1일</button>
            <button type="button" onClick={resetClock}>처음 시각</button>
          </div>
        </section>

        <section>
          <h2>장면 바로 가기</h2>
          <p className={styles.hint}>두 화면을 함께 옮겨요</p>
          <div className={styles.buttons}>
            {scenes.map((sc) => (
              <button key={sc.label} type="button" onClick={() => goBoth(sc.path)}>
                {sc.label}
              </button>
            ))}
          </div>
        </section>

        <section>
          <h2>처음으로</h2>
          <button type="button" className={styles.reset} onClick={reset}>
            기본
          </button>
          <p className={styles.hint}>데이터·시연 시계·타이머·점검 스위치를 모두 처음으로 돌려요</p>
        </section>

        <section>
          <h2>점검</h2>
          <label className={styles.check}>
            <input type="checkbox" checked={debug.fail} onChange={(e) => changeDebug({ fail: e.target.checked })} />
            AI 멈춤 흉내 (모든 요청 실패)
          </label>
          <label className={styles.check}>
            응답 늦게
            <select value={debug.slowMs} onChange={(e) => changeDebug({ slowMs: Number(e.target.value) })}>
              {SLOW_OPTIONS.map((ms) => (
                <option key={ms} value={ms}>
                  {ms === 0 ? '끔' : `${ms / 1000}초`}
                </option>
              ))}
            </select>
          </label>
          <div className={styles.buttons}>
            <button type="button" onClick={() => frames.forEach((f) => f.current?.contentWindow?.location.reload())}>
              두 화면 새로고침
            </button>
          </div>
          <p className={styles.hint}>
            데이터: {USE_MOCK ? '목 데이터' : '실서버 (실패하면 목 데이터)'}
            {(debug.fail || debug.slowMs > 0) && ' · 점검 스위치 켜짐'}
          </p>
        </section>

        <section>
          <h2>지금 데이터</h2>
          <dl className={styles.state}>
            {s.schedulings.map((c) => (
              <div key={c.id}>
                <dt>조율 {c.id}</dt>
                <dd>
                  {c.status}
                  {c.meetingId && ` → ${c.meetingId}`}
                </dd>
              </div>
            ))}
            {s.proposals.map((p) => {
              const m = s.meetings.find((x) => x.id === p.meetingId)
              return (
                <div key={p.meetingId}>
                  <dt>
                    회의안 {p.meetingId}
                    {m && ` · ${formatSlot(m.startAt, m.endAt)} · ${m.status}`}
                  </dt>
                  <dd>
                    {p.settled ? '조정 · ' : ''}
                    {Object.entries(p.responses)
                      .map(([id, st]) => `${nameOf(id)} ${st}`)
                      .join(', ')}
                  </dd>
                </div>
              )
            })}
          </dl>
        </section>
      </aside>
    </main>
  )
}
