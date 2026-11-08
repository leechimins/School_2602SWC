import { useEffect, useState } from 'react'
import { Outlet, useLocation, useNavigationType } from 'react-router-dom'
import { justBooted } from '../lib/boot.ts'
import { visit } from '../lib/trail.ts'
import TabBar from './TabBar.tsx'
import WriteFailNotice from './WriteFailNotice.tsx'
import styles from './AppShell.module.css'

type Props = {
  tabs?: boolean // 처음 화면(방 만들기·온보딩)은 하단 탭 없이 휴대폰 폭 틀만 쓴다
}

// 휴대폰 폭 앱 틀. 탭 아래 화면은 <Outlet />에 그려지고, 각 화면이 <Screen>으로 제목줄·본문을 정한다.
// 스플래시에서 막 넘어왔을 때만 부드럽게 나타난다.
export default function AppShell({ tabs = true }: Props) {
  const [entering] = useState(justBooted)
  useTrail()
  return (
    <div className={`${styles.app} ${entering ? styles.enter : ''}`}>
      <div className={styles.screen}>
        <Outlet />
        <WriteFailNotice />
      </div>
      {tabs && <TabBar />}
    </div>
  )
}

// 거쳐 온 주소를 쌓는다. 뒤로 버튼(Screen)이 이 목록으로 왔던 화면에 돌아간다
function useTrail() {
  const location = useLocation()
  const type = useNavigationType()
  useEffect(() => {
    const isBack = (location.state as { back?: boolean } | null)?.back === true
    const move = isBack ? 'back' : type === 'POP' ? 'pop' : type === 'REPLACE' ? 'replace' : 'push'
    visit(location.pathname + location.search, move)
  }, [location, type])
}
