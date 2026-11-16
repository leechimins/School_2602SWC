import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { takeBack } from '../lib/trail.ts'
import Icon from './Icon.tsx'
import styles from './Screen.module.css'

type Props = {
  title: string
  /** 왔던 화면을 모를 때(새로 고침·바로 연 주소) 돌아갈 주소. 있으면 제목 왼쪽에 뒤로 버튼이 생긴다 */
  backTo?: string
  /** 뒤로 버튼이 할 일을 화면이 직접 정할 때(온보딩 단계, 로그아웃 등). 있으면 backTo보다 먼저 쓴다 */
  onBack?: () => void
  /** 제목줄 오른쪽 (홈의 알림 종 등) */
  aux?: ReactNode
  /** 제목줄 대신 본문 맨 위에 두는 머리(홈의 보라 띠). 본문과 함께 스크롤된다 */
  hero?: ReactNode
  /** 탭 바로 위에 붙는 하단 고정 영역 (주요 행동 버튼) */
  dock?: ReactNode
  /** 하단 고정 영역을 흰 판 없이 버튼만 띄운다(버튼 하나뿐인 폼) */
  bareDock?: boolean
  children: ReactNode
}

// 화면 한 장의 틀: 상단 제목줄 → 스크롤되는 본문 → 하단 고정 영역
export default function Screen({ title, backTo, onBack, aux, hero, dock, bareDock = false, children }: Props) {
  const navigate = useNavigate()
  // 왔던 화면으로 간다(lib/trail.ts). 누를 때 꺼내야 방금 바뀐 주소까지 반영된다
  const goBack = () => {
    if (onBack) return onBack()
    if (backTo) navigate(takeBack() ?? backTo, { state: { back: true } })
  }
  const hasBack = Boolean(onBack || backTo)

  return (
    <div className={styles.screen}>
      {hero ? (
        <div />
      ) : (
        <header className={styles.top}>
          {hasBack && (
            <button type="button" className={styles.back} aria-label="뒤로" onClick={goBack}>
              <Icon name="back" />
            </button>
          )}
          <h1 className={styles.title}>{title}</h1>
          {aux}
        </header>
      )}
      <main className={styles.body}>
        {hero}
        {children}
      </main>
      {dock && (
        // 흰 판이 있을 때만 data-dock: 탭 바가 그 판에 선 하나로 이어 붙는다(TabBar.module.css)
        <div className={bareDock ? styles.bare : styles.dock} data-dock={bareDock ? undefined : true}>
          {dock}
        </div>
      )}
    </div>
  )
}
