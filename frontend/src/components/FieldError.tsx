import form from '../pages/Form.module.css'

/** 폼 안내 한 줄과 그 안내를 띄울 자리. at은 칸 이름이고, 서버 오류처럼 칸이 없는 안내는 'end'(맨 아래) */
export type FormProblem = { at: string; message: string } | null

// 폼 안내는 문제가 있는 칸 바로 아래에 뜬다(빈 이름은 이름 칸 아래, 시간 순서는 시간 줄 아래).
// 어느 칸 탓도 아닌 서버 오류만 맨 아래. 입력 창(InputSheet)도 같은 자리·모양이다
export default function FieldError({ problem, at }: { problem: FormProblem; at: string }) {
  if (problem?.at !== at) return null
  return (
    <p className={form.error} role="alert">
      {problem.message}
    </p>
  )
}
