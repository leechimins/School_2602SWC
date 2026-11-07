import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.tsx'
import { signIn } from './api/session.ts'
import { currentUserName } from './hooks/useCurrentUser.ts'
import './styles/tokens.css'
import './styles/base.css'

// 실서버 모드에서는 로그인하고 서버 번호를 받은 뒤에 그린다. 먼저 그리면 첫 화면이 목 ID(room-1)로 불러 400이 난다.
// 목 모드에서는 signIn이 바로 돌아온다.
void signIn(currentUserName()).finally(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </StrictMode>,
  )
})
