import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { takeBack } from '../lib/trail.ts'
import Icon from './Icon.tsx'
import styles from './Screen.module.css'

type Props = {
  title: string
  /** 왔던 화면을 모를 때(새로 고침·바로 연 주소) 돌아갈 주소. 있으면 제목 왼쪽에 뒤로 버튼이 생긴다 */
  backTo?: string
  /** 제목줄 오른쪽 (홈의 알림 종 등) */
  aux?: ReactNode
  /** 탭 바로 위에 붙는 하단 고정 영역 (주요 행동 버튼) */
  dock?: ReactNode
  children: ReactNode
}

// 화면 한 장의 틀: 상단 제목줄 → 스크롤되는 본문 → 하단 고정 영역
export default function Screen({ title, backTo, aux, dock, children }: Props) {
  const navigate = useNavigate()
  // 왔던 화면으로 간다(lib/trail.ts). 누를 때 꺼내야 방금 바뀐 주소까지 반영된다
  const goBack = () => backTo && navigate(takeBack() ?? backTo, { state: { back: true } })

  return (
    <div className={styles.screen}>
      <header className={styles.top}>
        {backTo && (
          <button type="button" className={styles.back} aria-label="뒤로" onClick={goBack}>
            <Icon name="back" />
          </button>
        )}
        <h1 className={styles.title}>{title}</h1>
        {aux}
      </header>
      <main className={styles.body}>{children}</main>
      {dock && <div className={styles.dock}>{dock}</div>}
    </div>
  )
}
