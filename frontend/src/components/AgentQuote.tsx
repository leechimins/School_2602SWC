import { josa, withJosa } from '../lib/korean.ts'
import type { Preferences } from '../types/me.ts'
import styles from './AgentQuote.module.css'

// 방식은 고르지 않았으면(null) 상관없음과 같다. 세 경우 모두 한 문장이 나온다
const MODE_TEXT = { 대면: '대면 회의', 비대면: '비대면 회의', 상관없음: '대면·비대면 모두' } as const

type Props = { name: string; prefs: Preferences }

// 내 에이전트가 조율에서 할 말. 조건 네 가지를 정해진 틀에 그대로 끼워 만든다(조건마다 한 문장, 고른 것만)
export default function AgentQuote({ name, prefs }: Props) {
  const { fromHour, toHour, mode, dayparts, avoid } = prefs
  const avoidText = avoid.trim().replace(/\.$/, '')
  // "화요일 오전은 어려워요"처럼 문장으로 썼으면 그대로, "화요일 오전"처럼 때만 썼으면 "…은 피하고 싶어요"를 붙인다
  const avoidIsSentence = /[요다]$/.test(avoidText)
  const when = dayparts.join('·')
  // 고른 조건만 한 문장씩
  const sentences = [
    fromHour !== null && toHour !== null && (
      <span key="hours">
        {withJosa(name, '은/는')} <em>{fromHour}시–{toHour}시</em>에 회의할 수 있어요.
      </span>
    ),
    <span key="mode">
      <em>{MODE_TEXT[mode ?? '상관없음']}</em>
      {mode === '대면' || mode === '비대면' ? '를 원해요.' : ' 괜찮아요.'}
    </span>,
    when && (
      <span key="when">
        <em>{when}</em> 시간대가 좋아요.
      </span>
    ),
    avoidText && (
      <span key="avoid">
        {avoidIsSentence ? (
          <em>{avoidText}.</em>
        ) : (
          <>
            <em>{avoidText}</em>
            {josa(avoidText, '은/는')} 피하고 싶어요.
          </>
        )}
      </span>
    ),
  ].filter(Boolean)

  return (
    <div className={styles.quote}>
      <p className={styles.head}>
        <b>내 에이전트가 이렇게 말해요</b>
      </p>
      <p>
        {sentences.length === 0 ? (
          '아직 고른 조건이 없어요. 조건이 없으면 비어 있는 시간 중에서 골라요.'
        ) : (
          <>“{sentences.flatMap((el, i) => (i === 0 ? [el] : [' ', el]))}”</>
        )}
      </p>
    </div>
  )
}
