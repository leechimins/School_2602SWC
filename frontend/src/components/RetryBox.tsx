type Props = {
  message?: string
  onRetry: () => void
}

// 불러오기 실패·AI 멈춤. 따로 오류 화면을 그리지 않고 한 줄 안내와 다시 하기 버튼만 둔다.
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
