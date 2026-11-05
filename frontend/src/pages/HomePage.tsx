import { Link } from 'react-router-dom'

export default function HomePage() {
  return (
    <main>
      <h1>팀플 에이전트</h1>
      <Link to="/demo">시연 화면으로</Link>
    </main>
  )
}
