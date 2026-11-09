import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { PATHS } from '../lib/paths.ts'
import Icon from './Icon.tsx'
import styles from './BrandHero.module.css'

type Props = {
  /** 머리 글: 홈은 인사말, 마이는 큰 제목 */
  head: ReactNode
  /** 안 읽은 알림 수. 0이면 종에 점이 없다 */
  unread: number
  /** 오른쪽 위에 내 정보 버튼도 둘지 (홈만) */
  profileButton?: boolean
  /** 머리 아래 카드들. 첫 카드가 머리 위로 올라와 캐릭터 손 아래 깔린다 */
  children: ReactNode
}

// TTAK 보라 머리(홈 · 마이 공통, 11/9 시안): 구름 배경 · 왼쪽 위 로고 · 오른쪽 위 둥근 버튼 · 오른쪽 캐릭터.
// 캐릭터(z 2)가 카드 묶음(z 1)보다 위에 그려져 손이 첫 카드 윗변에 걸친다.
export default function BrandHero({ head, unread, profileButton = false, children }: Props) {
  return (
    <>
      <header className={styles.hero}>
        <div className={styles.topBar}>
          <img className={styles.logo} src="/splash/logo.webp" alt="TTAK" />
          <div className={styles.actions}>
            <Link to={PATHS.notifications} className={styles.round} aria-label={`알림, 안 읽은 것 ${unread}개`}>
              <Icon name="bell" />
              {unread > 0 && <i className={styles.dot} aria-hidden="true" />}
            </Link>
            {profileButton && (
              <Link to={PATHS.me} className={styles.round} aria-label="내 정보">
                <Icon name="person" />
              </Link>
            )}
          </div>
        </div>
        <div className={styles.text}>{head}</div>
        <img className={styles.peek} src="/splash/peek.webp" alt="" aria-hidden="true" />
      </header>
      <div className={styles.cards}>{children}</div>
    </>
  )
}
