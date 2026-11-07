import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './components/AppShell.tsx'
import DemoPage from './demo/DemoPage.tsx'
import { PATHS } from './lib/paths.ts'
import ComingSoonPage from './pages/ComingSoonPage.tsx'
import HomePage from './pages/HomePage.tsx'
import MeetingPage from './pages/MeetingPage.tsx'
import MePage from './pages/MePage.tsx'
import NotificationsPage from './pages/NotificationsPage.tsx'
import ProposalPage from './pages/ProposalPage.tsx'
import RecordPage from './pages/RecordPage.tsx'
import SchedulePage from './pages/SchedulePage.tsx'
import SchedulingNewPage from './pages/SchedulingNewPage.tsx'
import SchedulingPage from './pages/SchedulingPage.tsx'
import StartPage from './pages/StartPage.tsx'
import TasksPage from './pages/TasksPage.tsx'
import TeamPage from './pages/TeamPage.tsx'

// 앱 전체 라우트 목록. 탭 아래 화면은 AppShell(하단 탭) 안에, 처음 화면과 시연 화면은 밖에 둔다.
// ComingSoonPage 자리는 해당 이슈에서 실제 화면으로 바꾼다.
export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
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
        <Route path={PATHS.myTasks} element={<ComingSoonPage title="내 할 일" backTo={PATHS.tasks} />} />
        {/* 나 탭 */}
        <Route path={PATHS.me} element={<MePage />} />
        <Route path={PATHS.team} element={<TeamPage />} />
      </Route>
      {/* 처음 화면: 하단 탭 없이 휴대폰 폭 틀만 */}
      <Route element={<AppShell tabs={false} />}>
        <Route path={PATHS.start} element={<StartPage />} />
        <Route path={PATHS.onboarding} element={<ComingSoonPage title="온보딩" backTo={PATHS.home} />} />
      </Route>
      <Route path={PATHS.demo} element={<DemoPage />} />
      <Route path="*" element={<Navigate to={PATHS.home} replace />} />
    </Routes>
  )
}
