import styles from './Avatar.module.css'

type Props = {
  name: string
  size?: 'small' | 'medium' | 'large'
}

// 팀원 표시: 이름 글자 하나. 색으로 사람을 나누지 않는다(색만으로 구분하지 않기)
export default function Avatar({ name, size = 'medium' }: Props) {
  return (
    <span className={`${styles.avatar} ${styles[size]}`} aria-hidden="true">
      {name.slice(0, 1) || '?'}
    </span>
  )
}
