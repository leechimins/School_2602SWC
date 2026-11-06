import { Link } from 'react-router-dom'
import Icon from '../components/Icon.tsx'
import Screen from '../components/Screen.tsx'
import { PATHS } from '../lib/paths.ts'

// 홈: 지금 무엇을 봐야 하는지 한 화면에
export default function HomePage() {
  const bell = (
    <Link to={PATHS.notifications} className="icon-btn" aria-label="알림">
      <Icon name="bell" />
    </Link>
  )

  return (
    <Screen title="서비스디자인 팀 프로젝트" aux={bell}>
      <section className="sec">
        <p className="meta">마감까지 남은 날과 다음 회의, 내 할 일이 여기에 보여요.</p>
      </section>
    </Screen>
  )
}
