# frontend

팀플 에이전트 웹앱(휴대폰 폭 화면). 서버가 없어도 목 데이터로 모든 화면과 시연(`/demo`)이 돕니다.

## 실행

Node.js 22 이상(팀 기준 24 LTS)이 필요합니다.

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173/demo
```

| 명령 | 하는 일 |
|---|---|
| `npm run dev` | 개발 서버 |
| `npm run build` | 타입 검사(`tsc -b`) + 빌드(`dist/`) |
| `npm run preview` | 빌드본 띄우기. 시연 당일에는 이것으로 띄웁니다 |
| `npm run lint` | oxlint |

## 화면 주소

- `/demo` — 시연 화면. 휴대폰 화면 2개(왼쪽 팀장 지수, 오른쪽 팀원 민지)와 시연 장치(시연 시계, 장면 바로 가기, "기본" 초기화, 점검 스위치)를 한 페이지에 띄웁니다. "기본"은 데이터·시계·걸어 둔 타이머·보는 사람·점검 스위치를 모두 처음으로 돌려, 새로고침 없이 장면 1·2를 몇 번이고 다시 할 수 있습니다.
- `/` — 앱 하나만 볼 때. `/?user=u-minji`처럼 보는 사람을 바꿀 수 있습니다.
- 앱 안 화면 주소는 `src/lib/paths.ts` 한 곳에 모여 있습니다.

## 목 데이터 / 실서버 전환

환경 변수 `VITE_API_URL` 하나로 바꿉니다(`src/api/client.ts`).

| `VITE_API_URL` | 동작 |
|---|---|
| 비어 있음 (기본) | 목 데이터만 씁니다. 서버 없이 시연 |
| `/api/v1` | 실서버를 부릅니다. 서버가 죽었거나 느리거나 주소가 틀리면 같은 목 데이터로 이어 갑니다 |

로컬 백엔드(`localhost:8000`)에 붙일 때:

```bash
cp .env.example .env.local    # .env.local은 커밋되지 않습니다
# .env.local 안에서 VITE_API_URL=/api/v1
npm run dev
```

`vite.config.ts`의 프록시가 `/api`를 `http://localhost:8000`으로 넘깁니다. 브라우저 입장에서는 같은 출처라 CORS 설정 없이 로그인 쿠키가 오갑니다(`dev`·`preview` 모두).

## 폴더 구조

```text
src/
├─ main.tsx, App.tsx   # 시작점, 라우팅
├─ pages/              # 화면 단위 (홈·회의 잡기·조율 확인·일정·회의록·할 일·나·팀 등)
├─ components/         # 여러 화면에서 쓰는 요소 (뱃지·알림 카드·할 일 행·확인 창 등)
├─ api/                # 서버 호출은 여기서만. client.ts가 목/실서버 전환·실패 시 목으로 이어 가기를 맡고,
│                      #   convert.ts가 서버 응답(snake_case)을 화면 데이터 모양으로 바꿉니다
├─ mock/               # 목 저장소(store) · 시연 시드(seed) · 데이터를 바꾸는 액션 표(actions) · 화면용 조회(views)
├─ types/              # 화면이 쓰는 데이터 모양
├─ hooks/              # useApi(불러오기) · useClock(시연 시계) · useCurrentUser(보는 사람) 등
├─ lib/                # 날짜·한국어 조사·화면 주소·타이머·점검 스위치 같은 작은 도구
├─ demo/               # 시연 화면(/demo)과 시연 장치
└─ styles/             # tokens.css(디자인 토큰) · base.css
```

### 읽는 순서

1. `src/api/client.ts` — 모든 서버 호출이 지나는 곳
2. `src/mock/actions.ts` — 목 모드에서 데이터를 바꾸는 동작 전부(서버 API 목록과 1:1)
3. `src/demo/DemoPage.tsx` — 시연이 어떻게 두 화면을 함께 움직이는지

## 규칙

- 화면은 `api/` 함수만 부르고, `fetch`·목 저장소를 직접 만지지 않습니다.
- "지금"은 `useClock()`·`getNow()`로만 얻습니다(시연 시계를 따라가게). 타이머는 `lib/timers.ts`의 `later`·`wait`를 써야 "기본"을 누를 때 함께 지워집니다.
- 브랜치·커밋·화면 용어 규칙은 저장소 루트 `CONTRIBUTING.md`를 따릅니다.
