// 시연 장치의 점검 스위치: 서버가 느릴 때·AI가 멈췄을 때 화면이 어떻게 보이는지 일부러 만들어 본다.
// /demo 패널에서 켜고, 휴대폰 화면(iframe)들은 요청할 때마다 localStorage에서 읽는다(같은 출처라 함께 쓴다).
// 평소에는 꺼져 있어 앱 동작에 영향이 없다.

export type DebugFlags = {
  slowMs: number // 모든 요청을 이만큼 늦게 답한다. 0 = 꺼짐
  fail: boolean // 모든 요청을 AI 멈춤(503)처럼 실패시킨다
}

const KEY = 'teamplay-debug'
export const DEBUG_OFF: DebugFlags = { slowMs: 0, fail: false }

export function getDebug(): DebugFlags {
  try {
    const saved = localStorage.getItem(KEY)
    return saved ? { ...DEBUG_OFF, ...(JSON.parse(saved) as Partial<DebugFlags>) } : DEBUG_OFF
  } catch {
    return DEBUG_OFF
  }
}

export function setDebug(flags: DebugFlags) {
  try {
    localStorage.setItem(KEY, JSON.stringify(flags))
  } catch {
    /* 저장소가 막혀 있으면 스위치만 안 먹는다 */
  }
}
