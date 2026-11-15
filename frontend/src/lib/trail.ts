// 뒤로 버튼이 "왔던 화면"으로 가게, 앱 안에서 거쳐 온 주소를 쌓아 둔다 (일정 탭에서 연 회의 일정 → 뒤로 → 일정 탭).
// 새로 고치면 비고, 그때는 화면이 정한 주소(backTo)로 간다.

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
