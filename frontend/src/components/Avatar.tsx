import styles from './Avatar.module.css'

type Props = {
  name: string
  size?: 'small' | 'medium' | 'large'
}

// 팀원 표시: 이름 글자 하나. 색으로 사람을 나누지 않는다(색만으로 구분하지 않기)
export default function Avatar({ name, size = 'medium' }: Props) {
  return (
    <span className={`${styles.avatar} ${styles[size]}`} aria-hidden="true">
      {initialOf(name)}
    </span>
  )
}

const HANGUL_NAME = /^[가-힣]+$/

/**
 * 동그라미에 넣을 글자. 이름은 성까지 한 칸으로 받으므로, 한글 세 글자 이상이면 성을 건너뛰고
 * 부르는 이름의 첫 글자를 쓴다: 이지민 → 지, 남궁민수 → 민. 두 글자(지수)·영문(Jimin)은 첫 글자.
 */
function initialOf(name: string): string {
  const n = name.replace(/\s+/g, '') // "이 지민"처럼 띄어 써도 같게
  if (!n) return '?'
  if (HANGUL_NAME.test(n) && n.length >= 3) return n[n.length - 2]
  return n[0].toUpperCase()
}
