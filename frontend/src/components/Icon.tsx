// 기능이 있는 곳(하단 탭·뒤로·알림 종·받아적기)과 홈 머리의 팀 이름 상자에만 쓰는 선 아이콘. 그 밖의 장식용으로 쓰지 않는다.
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
  team: (
    <>
      <circle cx="9" cy="8" r="3" />
      <path d="M3.5 19a5.5 5.5 0 0 1 11 0M16 5.5a3 3 0 0 1 0 5.5M17.5 14a5 5 0 0 1 3 5" />
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
