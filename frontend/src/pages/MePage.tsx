import { Link, useNavigate } from 'react-router-dom'
import { isRealServer } from '../api/client.ts'
import { signOut } from '../api/session.ts'
import Screen from '../components/Screen.tsx'
import { PATHS } from '../lib/paths.ts'

// 나 탭: 내 조건 (#30에서 채운다) · 팀 · 로그아웃
export default function MePage() {
  const navigate = useNavigate()
  const logout = async () => {
    await signOut()
    navigate(PATHS.login, { replace: true })
  }

  return (
    <Screen title="나">
      <section className="sec">
        <p className="meta">내 에이전트가 할 말과 주간 시간표가 여기에 보여요.</p>
        <Link to={PATHS.team} className="link">
          팀 보기
        </Link>
      </section>
      {/* 목 모드에는 로그인이 없어서 숨긴다 */}
      {isRealServer() && (
        <button type="button" className="btn quiet block" onClick={logout}>
          로그아웃
        </button>
      )}
    </Screen>
  )
}
