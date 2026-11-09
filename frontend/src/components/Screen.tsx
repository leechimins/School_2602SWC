import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import Icon from './Icon.tsx'
import styles from './Screen.module.css'

type Hero = {
  /** 큰 제목 아래 한 줄 설명 */
  sub?: string
  /** 큰 제목 왼쪽 아이콘 */
  icon?: ReactNode
}

/** 띠 머리 아래 요약 칸 하나: 숫자 · 이름 · 보조 색. onClick이 있으면 눌린다(할 일 필터) */
export type BandStat = {
  label: string
  value: number
  tint: 'blue' | 'pink' | 'mint' | 'yellow' | 'violet'
  onClick?: () => void
  pressed?: boolean
}

type Band = {
  sub?: string
  /** 비어 있으면(불러오는 중) 칸을 그리지 않는다 */
  stats?: BandStat[]
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
   * TTAK 머리(홈만): 보라 그라데이션 + 로고 + 왼쪽 캐릭터 + 오른쪽 큰 제목.
   * 본문 맨 위에 붙어 함께 스크롤되고, 첫 묶음(.sec)이 머리 위로 살짝 올라온다.
   */
  hero?: Hero
  /** 띠 머리(일정·할 일): 연한 그라데이션 + 큰 제목 + 설명 + 요약 칸. 캐릭터·로고는 없다 */
  band?: Band
  children: ReactNode
}

// 화면 한 장의 틀: 상단 제목줄(또는 TTAK 머리·띠 머리) → 스크롤되는 본문 → 하단 고정 영역
export default function Screen({ title, backTo, aux, dock, hero, band, children }: Props) {
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

  if (band) {
    const stats = band.stats ?? []
    return (
      <div className={`${styles.screen} ${styles.heroScreen}`}>
        <main className={styles.body}>
          <header className={styles.band}>
            <div className={styles.bandTop}>
              {back}
              <div className={styles.bandText}>
                <h1 className={styles.bandTitle}>{title}</h1>
                {band.sub && <p className={styles.bandSub}>{band.sub}</p>}
              </div>
              {aux && <span className={styles.bandAux}>{aux}</span>}
            </div>
          </header>
          {stats.length > 0 && (
            <div className={styles.stats}>
              {stats.map((st) =>
                st.onClick ? (
                  <button
                    key={st.label}
                    type="button"
                    className={styles.stat}
                    data-tint={st.tint}
                    aria-pressed={st.pressed ?? false}
                    onClick={st.onClick}
                  >
                    <StatBody stat={st} />
                  </button>
                ) : (
                  <div key={st.label} className={styles.stat} data-tint={st.tint}>
                    <StatBody stat={st} />
                  </div>
                ),
              )}
            </div>
          )}
          <div className={styles.bandBody}>{children}</div>
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

function StatBody({ stat }: { stat: BandStat }) {
  return (
    <>
      <span className={styles.statLabel}>
        <i className={styles.statDot} aria-hidden="true" />
        {stat.label}
      </span>
      <b className={`${styles.statValue} num`}>{stat.value}</b>
    </>
  )
}
