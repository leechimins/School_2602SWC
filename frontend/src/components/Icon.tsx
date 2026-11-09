// 선 아이콘. 기능이 있는 곳(하단 탭·뒤로·알림 종·받아적기)과, 글자와 함께 붙는 상태 표시(진행 중·막힘·완료)에 쓴다.
const PATHS = {
  home: <path d="M4 10.5 12 4l8 6.5V20h-5v-6H9v6H4z" />,
  calendar: (
    <>
      <rect x="4" y="5" width="16" height="15" rx="2" />
      <path d="M4 9.5h16M9 3v4M15 3v4" />
    </>
  ),
  tasks: (
    <>
      <rect x="4" y="4" width="16" height="16" rx="3" />
      <path d="m8.5 12 2.5 2.5 4.5-5" />
    </>
  ),
  person: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 20c1.5-4 4.5-6 8-6s6.5 2 8 6" />
    </>
  ),
  bell: <path d="M6 16v-5a6 6 0 0 1 12 0v5l1.5 2h-15zM10 20.5h4" />,
  back: <path d="M15 5l-7 7 7 7" />,
  mic: (
    <>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" />
    </>
  ),
  // 상태: 뱃지·필터 칩에서 글자 옆에 붙는다 (색만으로 구분하지 않기 — 글자는 늘 같이)
  progress: <circle cx="12" cy="12" r="7.5" strokeDasharray="2.6 3" />,
  alert: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 8v4.5M12 15.8v.2" />
    </>
  ),
  check: <path d="m5.5 12.5 4.2 4 8.8-9" />,
  chevron: <path d="m6 9.5 6 6 6-6" />,
  plus: <path d="M12 5v14M5 12h14" />,
  pencil: <path d="M5 19l1-4 9.5-9.5a2.1 2.1 0 0 1 3 3L9 18zM14 7l3 3" />,
  link: <path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" />,
  heart: <path d="M12 19.5s-7-4.3-7-9.3A3.9 3.9 0 0 1 12 8a3.9 3.9 0 0 1 7 2.2c0 5-7 9.3-7 9.3z" />,
} as const

export type IconName = keyof typeof PATHS

type Props = {
  name: IconName
  small?: boolean
}

export default function Icon({ name, small = false }: Props) {
  return (
    <svg className={small ? 'i s' : 'i'} viewBox="0 0 24 24" aria-hidden="true">
      {PATHS[name]}
    </svg>
  )
}
