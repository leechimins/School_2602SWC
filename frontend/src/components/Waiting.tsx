import styles from './Waiting.module.css'

type Props = {
  what: string // 무엇을 기다리는지: "회의록을 정리하고 있어요"
  detail?: string // 기다리는 동안 무엇을 볼 수 있는지: "원문은 아래에서 먼저 볼 수 있어요"
}

// 기다림 표시. 스피너로 화면을 덮지 않고 무엇을 기다리는지 글로 알린다.
// 기다림이 있는 화면은 넷뿐이다(시간 정하는 과정·받아적기·회의록 정리·할 일 뽑기). 바로 나오는 화면에는 쓰지 않는다.
export default function Waiting({ what, detail }: Props) {
  return (
    <div className={styles.waiting} role="status">
      <span className={styles.dots} aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      <div>
        <p className={styles.what}>{what}</p>
        {detail && <p className="meta">{detail}</p>}
      </div>
    </div>
  )
}
