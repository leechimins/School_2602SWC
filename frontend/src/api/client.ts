import { markChanged } from '../lib/changes.ts'

// 서버 호출은 이 파일을 거친다. 서버 주소는 환경 변수 VITE_API_URL, 비우면 /api/v1(vite 프록시가 로컬 백엔드로 넘긴다)
const API_URL = (import.meta.env.VITE_API_URL || '/api/v1').replace(/\/$/, '')

const TIMEOUT_MS = 5_000 // AI가 도는 요청(요약 등)은 호출하는 쪽에서 timeoutMs로 늘린다

export class ApiError extends Error {
  status: number
  code: string

  constructor(status: number, code: string, message: string) {
    super(message) // 서버 message는 화면에 그대로 띄울 한국어 한 줄이다(api-스펙 권장 규칙 1)
    this.status = status
    this.code = code
  }
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  timeoutMs?: number
}

/**
 * 서버 호출. 응답 JSON을 그대로 돌려주고, 프론트 타입으로 바꾸는 일은 convert.ts가 한다.
 * 네트워크 오류·시간 초과·JSON이 아닌 응답도 ApiError로 바꿔 화면이 한 줄 문구와 다시 하기를 보여 주게 한다.
 */
export async function request<Raw>(path: string, options: RequestOptions = {}): Promise<Raw> {
  let res: Response
  try {
    res = await fetch(`${API_URL}${path}`, {
      method: options.method ?? 'GET',
      credentials: 'include', // 세션 쿠키
      headers: { 'Content-Type': 'application/json' },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: AbortSignal.timeout(options.timeoutMs ?? TIMEOUT_MS),
    })
  } catch (e) {
    console.warn('[api] 서버에 닿지 않음', path, e)
    throw new ApiError(503, 'NETWORK', '잠시 후 다시 해 주세요.')
  }
  if (res.status === 204) return undefined as Raw

  const body: unknown = await res.json().catch(() => undefined)
  if (body === undefined) throw new ApiError(502, 'BAD_RESPONSE', '서버 응답을 읽을 수 없어요')
  if (!res.ok) {
    const err = body as { code?: string; message?: string }
    throw new ApiError(res.status, err.code ?? 'UNKNOWN', err.message ?? '잠시 후 다시 해 주세요.')
  }
  return body as Raw
}

/** 쓰기 요청. 성공하면 열린 화면들이 다시 불러오게 알린다 */
export async function write<T>(run: () => Promise<T>): Promise<T> {
  const result = await run()
  markChanged()
  return result
}

/** 화면에 띄울 한 줄. 알 수 없는 오류는 AI 멈춤과 같은 문구로 */
export function messageOf(e: unknown): string {
  if (e instanceof ApiError) return e.message
  if (e instanceof Error && e.message) return e.message
  return '잠시 후 다시 해 주세요.'
}
