import styles from './JudgeBubble.module.css'

type Props = {
  text: string // 이유 문장 (1~3문장의 사람 말)
  proposal?: string // 이번에 낸 시간: "11/18(수) 16:00–18:00 · 비대면"
  isNew?: boolean
}

// 판단 에이전트(중립)의 말. 팀원 말풍선과 모양을 달리해 누가 말하는지 바로 구분되게 한다.
// 낸 시간을 먼저 보이고, 그 아래에 이유 문장을 둔다
export default function JudgeBubble({ text, proposal, isNew = false }: Props) {
  return (
    <div className={`${styles.judge} ${isNew ? styles.enter : ''}`}>
      <div className={styles.head}>⚖ 판단 에이전트 (중립)</div>
      {proposal && (
        <div className={styles.box}>
          <div className={`${styles.yrow} ${styles.pick}`}>
            <span className="meta">고른 시간</span>
            <b className={`num ${styles.wide}`}>{proposal}</b>
          </div>
        </div>
      )}
      <p className={styles.say}>{text}</p>
    </div>
  )
}
