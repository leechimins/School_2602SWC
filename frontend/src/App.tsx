import { useSyncExternalStore, type ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { isRealServer } from './api/client.ts'
import { getIdentity, subscribeIdentity } from './api/session.ts'
import AppShell from './components/AppShell.tsx'
import DemoPage from './demo/DemoPage.tsx'
import { isBooted } from './lib/boot.ts'
import { PATHS } from './lib/paths.ts'
import HomePage from './pages/HomePage.tsx'
import MeetingPage from './pages/MeetingPage.tsx'
import MePage from './pages/MePage.tsx'
import NotificationsPage from './pages/NotificationsPage.tsx'
import OnboardingPage from './pages/OnboardingPage.tsx'
import ProposalPage from './pages/ProposalPage.tsx'
import RecordPage from './pages/RecordPage.tsx'
import SchedulePage from './pages/SchedulePage.tsx'
import SchedulingNewPage from './pages/SchedulingNewPage.tsx'
import SchedulingPage from './pages/SchedulingPage.tsx'
import SplashPage from './pages/SplashPage.tsx'
import StartPage from './pages/StartPage.tsx'
import TasksPage from './pages/TasksPage.tsx'

// 처음 열었으면 스플래시부터, 실서버인데 로그인 안 했으면 로그인부터. 가려던 주소는 state.from에 담아 돌아온다.
function RequireLogin({ children }: { children: ReactNode }) {
  const location = useLocation()
  const identity = useSyncExternalStore(subscribeIdentity, getIdentity)
  if (!isBooted() || (isRealServer() && !identity)) {
    return <Navigate to={PATHS.login} replace state={{ from: location.pathname + location.search }} />
  }
  return children
}

// 앱 전체 라우트 목록. 탭 아래 화면은 AppShell(하단 탭) 안에, 처음 화면과 시연 화면은 밖에 둔다.
export default function App() {
  return (
    <Routes>
      <Route
        element={
          <RequireLogin>
            <AppShell />
          </RequireLogin>
        }
      >
        {/* 홈 탭 */}
        <Route path={PATHS.home} element={<HomePage />} />
        <Route path={PATHS.notifications} element={<NotificationsPage />} />
        <Route path={PATHS.schedulingNew} element={<SchedulingNewPage />} />
        <Route path={PATHS.scheduling} element={<SchedulingPage />} />
        <Route path={PATHS.proposal} element={<ProposalPage />} />
        {/* 일정 탭 */}
        <Route path={PATHS.schedule} element={<SchedulePage />} />
        <Route path={PATHS.meeting} element={<MeetingPage />} />
        <Route path={PATHS.record} element={<RecordPage />} />
        {/* 할 일 탭 */}
        <Route path={PATHS.tasks} element={<TasksPage />} />
        {/* 나 탭 */}
        <Route path={PATHS.me} element={<MePage />} />
      </Route>
      {/* 처음 화면: 하단 탭 없이 휴대폰 폭 틀만 */}
      <Route
        element={
          <RequireLogin>
            <AppShell tabs={false} />
          </RequireLogin>
        }
      >
        <Route path={PATHS.start} element={<StartPage />} />
        <Route path={PATHS.onboarding} element={<OnboardingPage />} />
      </Route>
      <Route path={PATHS.login} element={<SplashPage />} />
      <Route path={PATHS.demo} element={<DemoPage />} />
      <Route path="*" element={<Navigate to={PATHS.home} replace />} />
    </Routes>
  )
}
