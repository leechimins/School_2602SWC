import { josa, withJosa } from '../lib/korean.ts'
import type { Preferences } from '../types/me.ts'
import styles from './AgentQuote.module.css'

const MODE_TEXT = { 대면: '대면으로 만나요', 비대면: '비대면으로 만나요', 상관없음: '대면·비대면 모두 괜찮아요' } as const

type Props = { name: string; prefs: Preferences }

// 내 에이전트가 조율에서 할 말. 조건 네 가지를 정해진 틀에 그대로 끼워 만든다(조건마다 한 문장, 고른 것만)
export default function AgentQuote({ name, prefs }: Props) {
  const { fromHour, toHour, mode, dayparts, avoid } = prefs
  const avoidText = avoid.trim()
  const when = dayparts.join('·')
  // 고른 조건만 한 문장씩
  const sentences = [
    fromHour !== null && toHour !== null && (
      <span key="hours">
        {withJosa(name, '은/는')} <em>{fromHour}시–{toHour}시</em> 사이에 회의할 수 있어요.
      </span>
    ),
    mode && (
      <span key="mode">
        <em>{MODE_TEXT[mode]}</em>.
      </span>
    ),
    when && (
      <span key="when">
        <em>{when}</em>
        {josa(when, '은/는')} 좋아요.
      </span>
    ),
    avoidText && (
      <span key="avoid">
        피하고 싶은 시간은 <em>‘{avoidText}’</em>라고 했어요. 팀원에게는 이 말을 그대로 보여 주지 않고 다듬어서 조율 근거로 써요.
      </span>
    ),
  ].filter(Boolean)

  // 11/9 TTAK: 캐릭터(내 에이전트)가 말하는 말풍선. AI가 만든 말이라 노란 테두리를 유지한다
  return (
    <div className={styles.wrap}>
      <img className={styles.face} src="/splash/peek.webp" alt="" aria-hidden="true" />
      <div className={styles.quote}>
        <p className="meta">내 에이전트가 이렇게 말해 줘요</p>
        <p>
          {sentences.length === 0 ? (
            '아직 고른 조건이 없어요. 조건이 없으면 비어 있는 시간 중에서 골라요.'
          ) : (
            <>“{sentences.flatMap((el, i) => (i === 0 ? [el] : [' ', el]))}”</>
          )}
        </p>
      </div>
    </div>
  )
}
