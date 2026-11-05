import { Link } from 'react-router-dom'

// 시연 화면(/demo): 휴대폰 화면 2개와 시연 장치를 한 페이지에 띄울 자리.
export default function DemoPage() {
  return (
    <main>
      <h1>시연 화면</h1>
      <Link to="/">처음으로</Link>
    </main>
  )
}
