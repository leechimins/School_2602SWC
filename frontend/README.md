# frontend

팀플 에이전트 웹앱(휴대폰 폭 화면). 모든 데이터는 백엔드(`../backend`)에서 받습니다. 백엔드를 먼저 띄워 주세요.

## 실행

Node.js 22 이상(팀 기준 24 LTS)이 필요합니다.

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

| 명령 | 하는 일 |
|---|---|
| `npm run dev` | 개발 서버 |
| `npm run build` | 타입 검사(`tsc -b`) + 빌드(`dist/`) |
| `npm run preview` | 빌드본 띄우기. 시연 당일에는 이것으로 띄웁니다 |
| `npm run lint` | oxlint |

## 화면 주소

앱 안 화면 주소는 `src/lib/paths.ts` 한 곳에 모여 있습니다.

## 서버 연결

`src/api/client.ts`가 `VITE_API_URL`(비우면 `/api/v1`)을 부릅니다. `vite.config.ts`의 프록시가 `/api`를 `http://localhost:8000`으로 넘겨, 브라우저 입장에서는 같은 출처라 CORS 설정 없이 로그인 쿠키가 오갑니다(`dev`·`preview` 모두). 배포한 백엔드에 바로 붙일 때만 `.env.local`에 주소를 넣습니다(`.env.example` 참고).

서버가 실패하면 화면마다 한 줄 안내와 "다시 하기"가 뜹니다. 로그인은 스플래시의 구글 로그인 하나입니다(서버 `POST /sessions/google`).

## 폴더 구조

```text
src/
├─ main.tsx, App.tsx   # 시작점, 라우팅
├─ pages/              # 화면 단위 (홈·회의 잡기·조율 확인·일정·회의록·할 일·나·팀 등)
├─ components/         # 여러 화면에서 쓰는 요소 (뱃지·알림 카드·할 일 행·확인 창 등)
├─ api/                # 서버 호출은 여기서만. client.ts가 호출·오류를 맡고,
│                      #   convert.ts가 서버 응답(snake_case)을 화면 데이터 모양으로 바꿉니다
├─ types/              # 화면이 쓰는 데이터 모양
├─ hooks/              # useApi(불러오기) · useClock(지금) · useCurrentUser(로그인한 사람) 등
├─ lib/                # 날짜·한국어 조사·화면 주소·타이머 같은 작은 도구
└─ styles/             # tokens.css(디자인 토큰) · base.css
```

### 읽는 순서

1. `src/api/client.ts` — 모든 서버 호출이 지나는 곳
2. `src/api/convert.ts` — 서버 응답을 화면 데이터로 바꾸는 곳
3. `src/hooks/useApi.ts` — 화면이 불러오기·실패·다시 하기를 다루는 법

## 규칙

- 화면은 `api/` 함수만 부르고, `fetch`를 직접 쓰지 않습니다.
- "지금"은 `useClock()`으로 얻습니다.
- 브랜치·커밋·화면 용어 규칙은 저장소 루트 `CONTRIBUTING.md`를 따릅니다.
