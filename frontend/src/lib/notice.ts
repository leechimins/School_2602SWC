// 화면 맨 아래 한 줄 알림(Toast가 그린다). 확인 창을 띄우지 않는 동작의 결과를 여기로 알린다.
//   토스트: showNotice('저장했어요') — 잠깐 떴다 사라진다
//   스낵바: showNotice('제안을 삭제했어요', { undo, onExpire }) — [되돌리기]를 함께 보이고,
//           되돌리지 않고 시간이 지나면(또는 다음 알림이 오면) onExpire로 실제 반영한다
export const NOTICE_EVENT = 'app:notice'

export type NoticeOptions = {
  undo?: () => void // [되돌리기]를 누르면 부른다
  onExpire?: () => void // 되돌리지 않고 끝나면 부른다
}

export type NoticeItem = NoticeOptions & { message: string }

export function showNotice(message: string, options: NoticeOptions = {}) {
  window.dispatchEvent(new CustomEvent<NoticeItem>(NOTICE_EVENT, { detail: { message, ...options } }))
}
