// 조사를 앞 글자의 받침에 맞춘다: 민지가 / 현우가 / '자료 조사'를 / '화면 시안 3종'을
// 알림 이유 한 줄처럼 이름·제목이 들어가는 문장에서 쓴다.

type Pair = '이/가' | '을/를' | '은/는' | '과/와' | '으로/로'

// 숫자는 읽는 소리로 받침을 정한다 (0 영, 1 일, 3 삼, 6 육, 7 칠, 8 팔)
const DIGIT_HAS_FINAL: Record<string, boolean> = {
  '0': true, '1': true, '2': false, '3': true, '4': false,
  '5': false, '6': true, '7': true, '8': true, '9': false,
}

function finalConsonant(word: string): { has: boolean; isRieul: boolean } {
  const last = word.trim().replace(/['"’”)\]]+$/, '').slice(-1)
  if (last in DIGIT_HAS_FINAL) return { has: DIGIT_HAS_FINAL[last], isRieul: '178'.includes(last) }
  const code = last.charCodeAt(0) - 0xac00
  if (code < 0 || code > 11171) return { has: false, isRieul: false } // 한글이 아니면 받침 없음으로 본다
  const final = code % 28
  return { has: final !== 0, isRieul: final === 8 }
}

/** 단어 뒤에 맞는 조사를 붙인다: withJosa('민지', '이/가') → '민지가' */
export function withJosa(word: string, pair: Pair): string {
  const [withFinal, withoutFinal] = pair.split('/')
  const { has, isRieul } = finalConsonant(word)
  // '으로/로'는 ㄹ 받침 뒤에서도 '로'
  const useFinal = pair === '으로/로' ? has && !isRieul : has
  return word + (useFinal ? withFinal : withoutFinal)
}

/** 조사만: josa('오후·저녁', '은/는') → '은' (단어를 강조 표시와 따로 그릴 때) */
export function josa(word: string, pair: Pair): string {
  return withJosa(word, pair).slice(word.length)
}
