// 화면 맨 아래 한 줄 알림(WriteFailNotice가 그린다). 오류가 아닌 안내도 같은 자리에 띄운다
export const NOTICE_EVENT = 'app:notice'

export function showNotice(message: string) {
  window.dispatchEvent(new CustomEvent<string>(NOTICE_EVENT, { detail: message }))
}
