import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import Icon from './Icon.tsx'
import styles from './Screen.module.css'

type Hero = {
  /** 큰 제목 아래 한 줄 설명 */
  sub?: string
  /** 큰 제목 왼쪽 아이콘 (회의 조율의 달력 등) */
  icon?: ReactNode
}

type Props = {
  title: string
  /** 뒤로 갈 주소. 있으면 제목 왼쪽에 뒤로 버튼이 생긴다 (iframe에서도 확실하게 주소로 돌아간다) */
  backTo?: string
  /** 제목줄 오른쪽 (홈의 알림 종 등) */
  aux?: ReactNode
  /** 탭 바로 위에 붙는 하단 고정 영역 (주요 행동 버튼) */
  dock?: ReactNode
  /**
   * TTAK 머리: 보라 그라데이션 + 로고 + 큰 제목 + 오른쪽에 걸친 캐릭터(11/9 시안).
   * 있으면 제목줄 대신 이 머리가 본문 맨 위에 붙어 함께 스크롤되고, 첫 묶음(.sec)이 캐릭터 손 아래로 올라온다.
   */
  hero?: Hero
  children: ReactNode
}

// 화면 한 장의 틀: 상단 제목줄(또는 TTAK 머리) → 스크롤되는 본문 → 하단 고정 영역
export default function Screen({ title, backTo, aux, dock, hero, children }: Props) {
  const back = backTo && (
    <Link to={backTo} className={styles.back} aria-label="뒤로">
      <Icon name="back" />
    </Link>
  )

  if (hero) {
    return (
      <div className={`${styles.screen} ${styles.heroScreen}`}>
        <main className={styles.body}>
          <header className={styles.hero}>
            <div className={styles.heroBar}>
              <span className={styles.heroSide}>{back}</span>
              <img className={styles.logo} src="/splash/logo.webp" alt="TTAK" />
              <span className={`${styles.heroSide} ${styles.heroAux}`}>{aux}</span>
            </div>
            <div className={styles.heroText}>
              <h1 className={styles.heroTitle}>
                {hero.icon && <span className={styles.heroIcon}>{hero.icon}</span>}
                {title}
              </h1>
              {hero.sub && <p className={styles.heroSub}>{hero.sub}</p>}
            </div>
            <img className={styles.peek} src="/splash/peek.webp" alt="" aria-hidden="true" />
          </header>
          <div className={styles.heroBody}>{children}</div>
        </main>
        {dock && <div className={styles.dock}>{dock}</div>}
      </div>
    )
  }

  return (
    <div className={styles.screen}>
      <header className={styles.top}>
        {back}
        <h1 className={styles.title}>{title}</h1>
        {aux}
      </header>
      <main className={styles.body}>{children}</main>
      {dock && <div className={styles.dock}>{dock}</div>}
    </div>
  )
}
