import { Link, useLocation } from 'react-router-dom'
import { PATHS, tabOf, type TabKey } from '../lib/paths.ts'
import Icon, { type IconName } from './Icon.tsx'
import styles from './TabBar.module.css'

// 하단 탭 네 개(브리프 "탭 구조"). 알림은 탭이 아니라 홈 오른쪽 위 종으로 들어간다.
const TABS: { key: TabKey; label: string; to: string; icon: IconName }[] = [
  { key: 'home', label: '홈', to: PATHS.home, icon: 'home' },
  { key: 'schedule', label: '일정', to: PATHS.schedule, icon: 'calendar' },
  { key: 'tasks', label: '할 일', to: PATHS.tasks, icon: 'tasks' },
  { key: 'me', label: '나', to: PATHS.me, icon: 'person' },
]

export default function TabBar() {
  const current = tabOf(useLocation().pathname)

  return (
    <nav className={styles.tabs} aria-label="하단 탭">
      {TABS.map((tab) => (
        <Link
          key={tab.key}
          to={tab.to}
          className={styles.tab}
          aria-current={tab.key === current ? 'page' : undefined}
        >
          <Icon name={tab.icon} />
          {tab.label}
        </Link>
      ))}
    </nav>
  )
}
