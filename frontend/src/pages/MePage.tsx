import { Link } from 'react-router-dom'
import Screen from '../components/Screen.tsx'
import { PATHS } from '../lib/paths.ts'

// 나 탭: 내 조건 (#30에서 채운다) · 팀
export default function MePage() {
  return (
    <Screen title="나">
      <section className="sec">
        <p className="meta">내 에이전트가 할 말과 주간 시간표가 여기에 보여요.</p>
        <Link to={PATHS.team} className="link">
          팀 보기
        </Link>
      </section>
    </Screen>
  )
}
