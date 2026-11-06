import { Outlet } from 'react-router-dom'
import TabBar from './TabBar.tsx'
import styles from './AppShell.module.css'

// 휴대폰 폭 앱 틀. 탭 아래 화면은 <Outlet />에 그려지고, 각 화면이 <Screen>으로 제목줄·본문을 정한다.
export default function AppShell() {
  return (
    <div className={styles.app}>
      <div className={styles.screen}>
        <Outlet />
      </div>
      <TabBar />
    </div>
  )
}
