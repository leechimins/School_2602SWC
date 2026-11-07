import type { ReactNode } from 'react'
import type { YieldChange } from '../types/scheduling.ts'
import YieldSteps from './YieldSteps.tsx'
import styles from './JudgeBubble.module.css'

type Props = {
  text: string // 이유 문장 (1~3문장의 사람 말)
  yieldChanges?: YieldChange[]
  proposal?: string // 이번에 낸 시간: "11/18(수) 16:00–18:00 · 비대면"
  isNew?: boolean
  children?: ReactNode // 결과 화면에서 덧붙이는 상자
}

// 판단 에이전트(중립)의 말. 팀원 말풍선과 모양을 달리해 누가 말하는지 바로 구분되게 한다.
// 양보 점수 변화와 낸 시간을 먼저 보이고, 그 아래에 이유 문장을 둔다
export default function JudgeBubble({ text, yieldChanges = [], proposal, isNew = false, children }: Props) {
  const hasBox = yieldChanges.length > 0 || proposal
  return (
    <div className={`${styles.judge} ${isNew ? styles.enter : ''}`}>
      <div className={styles.head}>⚖ 판단 에이전트 (중립)</div>
      {hasBox && (
        <div className={styles.box}>
          {yieldChanges.length > 0 && (
            <>
              <p className="meta">양보 점수</p>
              {yieldChanges.map((y) => (
                <div key={y.userId} className={styles.yrow}>
                  <span>{y.name}</span>
                  <YieldSteps level={y.to} />
                  <span>
                    {y.from === y.to ? (
                      y.to
                    ) : (
                      <>
                        {y.from} → <b>{y.to}</b>
                      </>
                    )}
                  </span>
                </div>
              ))}
            </>
          )}
          {proposal && (
            <div className={styles.yrow}>
              <span className="meta">고른 시간</span>
              <b className={`num ${styles.wide}`}>{proposal}</b>
            </div>
          )}
        </div>
      )}
      <p className={styles.say}>{text}</p>
      {children}
    </div>
  )
}
