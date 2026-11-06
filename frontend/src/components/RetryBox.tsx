type Props = {
  message?: string
  onRetry: () => void
}

// 불러오기 실패·AI 멈춤. 따로 오류 화면을 그리지 않고 한 줄 안내와 다시 하기 버튼만 둔다.
// 시연에서는 서버가 실패해도 목 데이터로 이어 가므로 거의 보이지 않는다.
export default function RetryBox({ message = '잠시 후 다시 해 주세요.', onRetry }: Props) {
  return (
    <section className="sec" role="alert">
      <p>{message}</p>
      <button type="button" className="btn small block" onClick={onRetry}>
        다시 하기
      </button>
    </section>
  )
}
