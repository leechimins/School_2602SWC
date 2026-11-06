// 여러 도메인이 같이 쓰는 기본 모양. 서버 ID는 숫자지만 프론트는 문자열로 받아 안을 들여다보지 않는다.
export type Id = string

/** YYYY-MM-DD */
export type IsoDate = string

/** ISO 8601 + 오프셋: 2026-11-10T16:00:00+09:00 */
export type IsoDateTime = string

export type MeetingMode = '대면' | '비대면'
