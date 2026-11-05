import { Navigate, Route, Routes } from 'react-router-dom'
import HomePage from './pages/HomePage.tsx'
import DemoPage from './demo/DemoPage.tsx'

// 앱 전체 라우트 목록. 화면이 늘면 여기에 한 줄씩 추가한다.
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/demo" element={<DemoPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
