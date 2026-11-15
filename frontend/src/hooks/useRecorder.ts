import { useEffect, useRef, useState } from 'react'

/**
 * 브라우저 녹음(MediaRecorder). start로 마이크를 열고, stop이 녹음 파일 하나를 돌려준다.
 * 음성은 서버에 올려 받아적은 뒤 버려진다. 화면을 떠나면 마이크를 닫는다.
 */
export function useRecorder() {
  const recorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const [startedAt, setStartedAt] = useState<number | null>(null)

  const release = () => recorder.current?.stream.getTracks().forEach((t) => t.stop())
  useEffect(() => release, [])

  /** 마이크를 열고 녹음을 시작한다. 마이크를 거부하면 한 줄 안내와 함께 실패한다 */
  const start = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true }).catch(() => {
      throw new Error('마이크를 쓸 수 있게 허락해 주세요.')
    })
    const r = new MediaRecorder(stream)
    chunks.current = []
    r.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.current.push(e.data)
    }
    r.start(1000) // 1초마다 조각을 받아 둔다(멈출 때 한꺼번에 받다 잃지 않게)
    recorder.current = r
    setStartedAt(Date.now())
  }

  /** 녹음을 멈추고 지금까지의 파일을 돌려준다 */
  const stop = () =>
    new Promise<Blob>((resolve) => {
      const r = recorder.current
      if (!r) return resolve(new Blob())
      r.onstop = () => {
        release()
        recorder.current = null
        resolve(new Blob(chunks.current, { type: r.mimeType.split(';')[0] }))
      }
      r.stop()
      setStartedAt(null)
    })

  return { start, stop, startedAt }
}
