// 서버에 쓰기를 마치면 올리는 번호. useApi가 이 번호를 보고 열린 화면들을 다시 불러온다.

const listeners = new Set<() => void>()
let revision = 0

export function getRevision(): number {
  return revision
}

export function markChanged() {
  revision += 1
  listeners.forEach((fn) => fn())
}

export function subscribeChanges(fn: () => void): () => void {
  listeners.add(fn)
  return () => {
    listeners.delete(fn)
  }
}
