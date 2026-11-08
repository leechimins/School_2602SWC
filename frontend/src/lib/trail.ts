// 뒤로 버튼이 "왔던 화면"으로 가게, 앱 안에서 거쳐 온 주소를 쌓아 둔다 (일정 탭에서 연 회의 일정 → 뒤로 → 일정 탭).
// 브라우저 history.back()은 쓰지 않는다: /demo의 휴대폰 두 대(iframe)가 기록 하나를 같이 써서 다른 휴대폰이 되돌아갈 수 있다.
// iframe마다 JS가 따로 돌아서 이 목록도 휴대폰마다 따로다. 새로 고치면 비고, 그때는 화면이 정한 주소(backTo)로 간다.

export type Move = 'push' | 'replace' | 'back' | 'pop'

const trail: string[] = []
let current: string | null = null

/** 주소가 바뀔 때마다 AppShell이 부른다 */
export function visit(path: string, move: Move) {
  if (current !== null && current !== path) {
    if (move === 'push') trail.push(current)
    if (move === 'pop') trail.pop() // 브라우저 뒤로 가기
  }
  current = path
}

/** 뒤로 버튼: 왔던 주소를 꺼낸다. 없으면 undefined */
export function takeBack(): string | undefined {
  return trail.pop()
}
