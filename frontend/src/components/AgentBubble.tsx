import { BURDEN_LABEL, BURDEN_TONE } from '../lib/tones.ts'
import type { Utterance } from '../types/scheduling.ts'
import Avatar from './Avatar.tsx'
import Badge from './Badge.tsx'
import styles from './AgentBubble.module.css'

type Props = {
  utterance: Utterance // kind가 appeal 또는 answer
  isMine: boolean
  isNew: boolean // 방금 나온 발언만 올라오며 나타난다
}

// 팀원 에이전트 말풍선. 응답이면 이름 옆 뱃지 하나에 응답과 불편 정도(내 것만 숫자)를 함께 둔다
export default function AgentBubble({ utterance: u, isMine, isNew }: Props) {
  const name = u.speakerName ?? ''
  const burden = isMine && u.myScore !== null ? `내 불편 ${u.myScore}/5` : u.burden && BURDEN_LABEL[u.burden]
  const tone = u.answer === '거절' ? 'danger' : u.burden ? BURDEN_TONE[u.burden] : 'ok'

  return (
    <div className={`${styles.msg} ${isMine ? styles.mine : ''} ${isNew ? styles.enter : ''}`}>
      {!isMine && <Avatar name={name} size="small" />}
      <div className={styles.body}>
        <div className={styles.who}>
          <span className={styles.name}>{isMine ? '내 에이전트' : `${name}의 에이전트`}</span>
          {u.answer && (
            <Badge tone={tone}>
              {u.answer} · <span className="num">{burden}</span>
            </Badge>
          )}
        </div>
        <p className={styles.text}>{u.text}</p>
      </div>
    </div>
  )
}
