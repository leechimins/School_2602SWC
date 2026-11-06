import Screen from '../components/Screen.tsx'

type Props = {
  title: string
  backTo?: string
}

// 경로만 먼저 잡아 둔 화면. 해당 이슈(#25·#26·#30)에서 실제 화면으로 바꾼다.
export default function ComingSoonPage({ title, backTo }: Props) {
  return (
    <Screen title={title} backTo={backTo}>
      <section className="sec">
        <p className="meta">이 화면은 아직 만드는 중이에요.</p>
      </section>
    </Screen>
  )
}
