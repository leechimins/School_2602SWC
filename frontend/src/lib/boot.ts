// 앱이 이번에 처음 뜬 뒤 스플래시(/login)를 한 번 지났는지.
// 처음 열면 어느 주소든 스플래시를 먼저 보여 주고, 지난 뒤에는 앱 안을 오가도 다시 보이지 않는다.

let booted = false
let bootedAt = 0

// 폰은 다른 앱에 갔다 오면 페이지를 새로 띄우기도 해서 위 값이 사라진다.
// 그래서 앱을 마지막으로 본 시각을 남겨 두고, 금방 돌아왔으면 스플래시를 건너뛴다.
const LAST_SEEN_KEY = 'ttak.lastSeen'
const RECENT_MS = 30 * 60 * 1000 // 30분 안에 돌아오면 "다시 연 것"이 아니라 "잠깐 나갔다 온 것"

function rememberSeen() {
  try {
    localStorage.setItem(LAST_SEEN_KEY, String(Date.now()))
  } catch {
    // 저장이 막힌 브라우저(사생활 보호 창 등): 매번 스플래시를 보여 주면 된다
  }
}

// 앱이 가려질 때(다른 앱으로, 화면 끔) 시각을 남긴다
document.addEventListener('visibilitychange', () => {
  if (booted && document.visibilityState === 'hidden') rememberSeen()
})
window.addEventListener('pagehide', () => {
  if (booted) rememberSeen()
})

export function isBooted(): boolean {
  return booted
}

export function markBooted() {
  booted = true
  bootedAt = Date.now()
  rememberSeen()
}

/** 30분 안에 앱을 보다가 돌아왔는지. 그렇다면 스플래시 캐릭터를 다시 보여 주지 않는다 */
export function cameBackSoon(): boolean {
  try {
    const at = Number(localStorage.getItem(LAST_SEEN_KEY))
    return at > 0 && Date.now() - at < RECENT_MS
  } catch {
    return false
  }
}

/** 스플래시에서 막 넘어왔는지. 앱 틀(AppShell)이 이때만 페이드인한다 — 앱 안을 오갈 때는 깜빡이지 않게 */
export function justBooted(): boolean {
  return bootedAt > 0 && Date.now() - bootedAt < 1000
}
