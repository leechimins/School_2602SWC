import Screen from '../components/Screen.tsx'

// 할 일 탭: 팀 할 일
export default function TasksPage() {
  return (
    <Screen title="할 일">
      <section className="sec">
        <p className="meta">확정된 할 일이 사람별로 묶여 보여요.</p>
      </section>
    </Screen>
  )
}
