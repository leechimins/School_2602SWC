import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import Icon from './Icon.tsx'
import styles from './Screen.module.css'

type Props = {
  title: string
  /** 뒤로 갈 주소. 있으면 제목 왼쪽에 뒤로 버튼이 생긴다 (iframe에서도 확실하게 주소로 돌아간다) */
  backTo?: string
  /** 제목줄 오른쪽 (홈의 알림 종 등) */
  aux?: ReactNode
  /** 탭 바로 위에 붙는 하단 고정 영역 (주요 행동 버튼) */
  dock?: ReactNode
  children: ReactNode
}

// 화면 한 장의 틀: 상단 제목줄 → 스크롤되는 본문 → 하단 고정 영역
export default function Screen({ title, backTo, aux, dock, children }: Props) {
  return (
    <div className={styles.screen}>
      <header className={styles.top}>
        {backTo && (
          <Link to={backTo} className={styles.back} aria-label="뒤로">
            <Icon name="back" />
          </Link>
        )}
        <h1 className={styles.title}>{title}</h1>
        {aux}
      </header>
      <main className={styles.body}>{children}</main>
      {dock && <div className={styles.dock}>{dock}</div>}
    </div>
  )
}
