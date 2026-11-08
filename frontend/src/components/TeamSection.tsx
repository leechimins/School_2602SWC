import { Link } from 'react-router-dom'
import { PATHS } from '../lib/paths.ts'
import type { Room } from '../types/room.ts'
import Avatar from './Avatar.tsx'
import Badge from './Badge.tsx'
import YieldSteps from './YieldSteps.tsx'
import styles from './TeamSection.module.css'

// 나 탭의 팀: 팀원 목록과 사람별 누적 양보 단계, 초대 코드.
// 역할은 보여 주지 않고 팀장 뱃지만 붙인다. 누적 양보는 숫자 없이 단계로만 보인다.
export default function TeamSection({ room }: { room: Room }) {
  return (
    <>
      <section className="sec">
        <div className="row-between">
          <h2>팀원</h2>
          <span className="meta num">
            {room.joinedCount}/{room.memberCount} 들어옴
          </span>
        </div>
        <ul className={styles.list}>
          {room.members.map((m) => (
            <li key={m.id} className={styles.member}>
              <Avatar name={m.name} size="large" />
              <span className={styles.name}>
                <span className="strong">
                  {m.name}
                  {m.isMe && ' (나)'}
                </span>
                {m.isLeader && <Badge tone="here">팀장</Badge>}
              </span>
              <span className={styles.yield}>
                <YieldSteps level={m.yieldLevel} />
                <span className="meta">{m.yieldLevel}</span>
              </span>
            </li>
          ))}
        </ul>
        <p className="meta">
          막대는 지금까지 회의 시간을 얼마나 맞춰 줬는지예요. 많이 맞춰 준 사람을 다음 조율에서 먼저 챙겨요.{' '}
          <Link to={PATHS.notifications} className="link">
            양보 기록 보기
          </Link>
        </p>
      </section>

      <section className="sec">
        <h2>팀원 초대</h2>
        <p className={`${styles.code} num`}>{room.inviteCode}</p>
        <p className="meta">팀원은 이 초대 코드로 들어와요.</p>
      </section>
    </>
  )
}
