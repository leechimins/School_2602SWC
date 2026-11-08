import { getDebug } from '../lib/debug.ts'
import { wait } from '../lib/timers.ts'
import { markChanged } from '../mock/store.ts'

// 서버 호출은 이 파일을 거친다. 목·실서버 전환과 서버 실패 시 목 데이터로 이어 가기를 여기 한 곳에서 한다.
//
// 전환은 환경 변수 하나: VITE_API_URL
//   비어 있으면(기본)     → 목 데이터만 쓴다. 서버 없이 시연이 돈다
//   주소가 있으면          → 실서버를 부르고, 서버가 죽었거나 느리거나 주소가 틀렸으면 같은 목 데이터로 이어 간다
const API_URL = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')
export const USE_MOCK = API_URL === ''

// 실서버 모드인데 처음에 서버가 안 닿아 "나는 누구"(GET /me)를 못 받았으면, 그 화면은 끝까지 목으로만 돈다.
// 신원 없이 서버를 부르면 목 ID(room-1 같은)가 서버로 가서 400이 나고, 목과 서버 번호가 섞인다.
let serverDown = false

/** 신원을 못 받았을 때 api/session.ts가 부른다 */
export function fallBackToMock() {
  serverDown = true
}

/** 지금 실서버로 도는지. 목 모드이거나 서버가 처음부터 안 닿았으면 false */
export function isRealServer(): boolean {
  return !USE_MOCK && !serverDown
}

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

/** 실서버 호출. 응답 JSON을 그대로 돌려주고, 프론트 타입으로 바꾸는 일은 convert.ts가 한다 */
export async function request<Raw>(path: string, options: RequestOptions = {}): Promise<Raw> {
  const res = await fetch(`${API_URL}${path}`, {
    method: options.method ?? 'GET',
    credentials: 'include', // 세션 쿠키
    headers: { 'Content-Type': 'application/json' },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: AbortSignal.timeout(options.timeoutMs ?? TIMEOUT_MS),
  })
  if (res.status === 204) return undefined as Raw

  const body: unknown = await res.json().catch(() => undefined)
  if (body === undefined) {
    // JSON이 아니다: 주소가 틀려 다른 페이지(HTML)가 왔다. 서버 실패로 보고 목 데이터로 넘긴다
    throw new ApiError(502, 'BAD_RESPONSE', '서버 응답을 읽을 수 없어요')
  }
  if (!res.ok) {
    const err = body as { code?: string; message?: string }
    throw new ApiError(res.status, err.code ?? 'UNKNOWN', err.message ?? '잠시 후 다시 시도해 주세요')
  }
  return body as Raw
}

/**
 * 실서버를 부르고, 실패하면 같은 목 데이터로 이어 간다.
 * - 이어 가는 경우: 네트워크 오류, 시간 초과, 5xx(AI 멈춤 503 포함), JSON이 아닌 응답
 * - 이어 가지 않는 경우: 서버가 code를 붙여 보낸 4xx(권한·입력 오류) → 그대로 던져 화면이 문구를 보여 준다
 *   (code 없는 4xx는 틀린 주소의 404 같은 것이라 서버 실패로 본다)
 */
export async function withMock<T>(real: () => Promise<T>, mock: () => T): Promise<T> {
  await debugGate()
  if (!isRealServer()) return mock()
  try {
    return await real()
  } catch (e) {
    if (e instanceof ApiError && e.status < 500 && e.code !== 'UNKNOWN') throw e
    console.warn('[api] 서버 실패 → 목 데이터로 이어 감', e)
    return mock()
  }
}

/** /demo 점검 스위치: 켜져 있으면 느리게 답하거나 AI 멈춤처럼 실패한다. 목 이어 가기보다 앞에 둬서 실패 화면이 보이게 한다 */
async function debugGate() {
  const { slowMs, fail } = getDebug()
  if (slowMs > 0) await wait(slowMs)
  if (fail) throw new ApiError(503, 'DEBUG_FAIL', '잠시 후 다시 해 주세요.')
}

/**
 * 쓰기 요청. 목 모드는 목 데이터에 쓰고(dispatch가 화면들에 알린다), 실서버 모드는 실패해도 목으로 이어 가지 않는다.
 * 읽기는 서버에서 오는데 쓰기만 목에 들어가면 "된 것처럼" 보이고 서버에는 없다(AI 실패 "정리 못 함"도 안 나온다).
 * 성공하면 다른 화면(다른 iframe 포함)이 다시 불러오게 알린다.
 */
export async function withMockWrite<T>(real: () => Promise<T>, mock: () => T): Promise<T> {
  await debugGate()
  if (!isRealServer()) return mock()
  try {
    const result = await real()
    markChanged()
    return result
  } catch (e) {
    if (e instanceof ApiError) throw e
    console.warn('[api] 쓰기 실패', e) // 네트워크 오류·시간 초과
    throw new ApiError(503, 'NETWORK', '잠시 후 다시 해 주세요.')
  }
}

/** 화면에 띄울 한 줄. 알 수 없는 오류는 AI 멈춤과 같은 문구로 */
export function messageOf(e: unknown): string {
  if (e instanceof ApiError) return e.message
  if (e instanceof Error && e.message) return e.message
  return '잠시 후 다시 해 주세요.'
}
