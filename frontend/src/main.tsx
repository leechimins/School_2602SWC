import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.tsx'
import { signIn } from './api/session.ts'
import { currentUserName } from './hooks/useCurrentUser.ts'
import { markBooted } from './lib/boot.ts'
import { PATHS } from './lib/paths.ts'
import './styles/tokens.css'
import './styles/base.css'

function render() {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </StrictMode>,
  )
}

// 시연 장치(/demo와 그 안의 휴대폰 화면 ?user=)는 스플래시 없이 그 사람으로 바로 들어간다.
// 이때는 로그인하고 서버 번호를 받은 뒤에 그린다. 먼저 그리면 첫 화면이 목 ID(room-1)로 불러 400이 난다.
// 그 밖에는 바로 그리고, 스플래시(SplashPage)가 2초 동안 쿠키를 확인한다.
const demo = window.location.pathname.startsWith(PATHS.demo) || new URLSearchParams(window.location.search).has('user')
if (demo) {
  markBooted()
  void signIn(currentUserName()).finally(render)
} else {
  render()
}
