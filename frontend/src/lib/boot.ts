// 앱이 이번에 처음 뜬 뒤 스플래시(/login)를 한 번 지났는지.
// 처음 열면 어느 주소든 스플래시를 먼저 보여 주고, 지난 뒤에는 앱 안을 오가도 다시 보이지 않는다.
// 시연 장치(/demo, ?user=)는 main.tsx가 처음부터 지난 것으로 둔다 — 휴대폰 화면마다 2초씩 기다리면 시연이 끊긴다.

let booted = false
let bootedAt = 0

export function isBooted(): boolean {
  return booted
}

export function markBooted() {
  booted = true
  bootedAt = Date.now()
}

/** 스플래시에서 막 넘어왔는지. 앱 틀(AppShell)이 이때만 페이드인한다 — 앱 안을 오갈 때는 깜빡이지 않게 */
export function justBooted(): boolean {
  return bootedAt > 0 && Date.now() - bootedAt < 1000
}
