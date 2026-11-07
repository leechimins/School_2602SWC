import { Link } from 'react-router-dom'
import { getRoom } from '../api/rooms.ts'
import Avatar from '../components/Avatar.tsx'
import Badge from '../components/Badge.tsx'
import RetryBox from '../components/RetryBox.tsx'
import Screen from '../components/Screen.tsx'
import YieldSteps from '../components/YieldSteps.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { PATHS } from '../lib/paths.ts'
import styles from './TeamPage.module.css'

// 팀(나 탭 아래): 팀원 목록과 초대, 사람별 누적 양보 단계.
// 역할은 보여 주지 않고 팀장 뱃지만 붙인다. 누적 양보는 숫자 없이 단계로만 보인다.
export default function TeamPage() {
  const user = useCurrentUser()
  const room = useApi(() => getRoom(user.roomId), [user.roomId, user.id])

  return (
    <Screen title="팀" backTo={PATHS.me}>
      {room.status === 'error' && <RetryBox message={room.message} onRetry={room.reload} />}
      {room.status === 'ready' && (
        <>
          <section className="sec">
            <div className="row-between">
              <h2>팀원</h2>
              <span className="meta num">
                {room.data.joinedCount}/{room.data.memberCount} 들어옴
              </span>
            </div>
            <ul className={styles.list}>
              {room.data.members.map((m) => (
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
            <p className="meta">막대는 지금까지 회의 시간을 얼마나 맞춰 줬는지예요. 많이 맞춰 준 사람을 다음 조율에서 먼저 챙겨요.</p>
          </section>

          <section className="sec">
            <h2>팀원 초대</h2>
            <p className={`${styles.code} num`}>{room.data.inviteCode}</p>
            <p className="meta">팀원은 이 초대 코드로 들어와요.</p>
          </section>

          <section className="sec">
            <p className="meta">회의마다 누가 왜 맞춰 줬는지는 알림의 양보 기록에서 봐요.</p>
            <Link to={PATHS.notifications} className="link">
              양보 기록 보기
            </Link>
          </section>
        </>
      )}
    </Screen>
  )
}
