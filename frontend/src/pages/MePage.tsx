import { Link, useNavigate } from 'react-router-dom'
import { isRealServer } from '../api/client.ts'
import { getRoom } from '../api/rooms.ts'
import { signOut } from '../api/session.ts'
import Avatar from '../components/Avatar.tsx'
import Icon, { type IconName } from '../components/Icon.tsx'
import Screen from '../components/Screen.tsx'
import { useApi } from '../hooks/useApi.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { PATHS } from '../lib/paths.ts'
import styles from './MePage.module.css'

const MENU: { to: string; icon: IconName; label: string }[] = [
  { to: PATHS.mePrefs, icon: 'heart', label: '내 조건 / 선호 설정' },
  { to: PATHS.meSchedule, icon: 'calendar', label: '시간표 연동' },
  { to: PATHS.team, icon: 'person', label: '팀 보기' },
]

// 마이 탭(11/9 시안): 프로필 → 메뉴(내 조건 · 시간표 연동 · 팀) → 로그아웃. 내용은 각 하위 화면에 있다
export default function MePage() {
  const user = useCurrentUser()
  const navigate = useNavigate()
  const room = useApi(() => getRoom(user.roomId), [user.roomId, user.id])

  const logout = async () => {
    await signOut()
    navigate(PATHS.login, { replace: true })
  }

  return (
    <Screen title="마이" band={{ sub: '내 정보와 팀 활동을 관리해요.' }}>
      <Link to={PATHS.team} className={`sec ${styles.profile}`}>
        <span className={styles.bigAvatar}>
          <Avatar name={user.name} size="large" />
        </span>
        <span className={styles.who}>
          <b className={styles.name}>{user.name}</b>
          <span className="meta">
            {room.status === 'ready' ? `${room.data.name} · ` : ''}
            {user.isLeader ? '팀장' : '팀원'}
          </span>
        </span>
        <span className={styles.chev} aria-hidden="true">
          <Icon name="back" small />
        </span>
      </Link>

      <nav className={`sec ${styles.menu}`} aria-label="마이 메뉴">
        {MENU.map((item) => (
          <Link key={item.to} to={item.to} className={styles.item}>
            <span className={styles.itemIcon} aria-hidden="true">
              <Icon name={item.icon} />
            </span>
            <span className={styles.itemLabel}>{item.label}</span>
            <span className={styles.chev} aria-hidden="true">
              <Icon name="back" small />
            </span>
          </Link>
        ))}
      </nav>

      {/* 목 모드에는 로그인이 없어서 숨긴다 */}
      {isRealServer() && (
        <div className={styles.logout}>
          <button type="button" className="btn quiet" onClick={logout}>
            로그아웃
          </button>
        </div>
      )}
    </Screen>
  )
}
