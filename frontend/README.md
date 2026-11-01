# frontend

팀플 에이전트 웹앱(휴대폰 폭 화면). 프로젝트는 아직 생성 전이며, 아래 스택과 구조로 만듭니다.

## 스택

Vite + React + TypeScript, React Router, CSS 변수(디자인 토큰) + CSS Modules, dayjs, Node.js 24 LTS

## 폴더 구조 (예정)

```text
frontend/
└─ src/
   ├─ pages/        # 화면 단위
   ├─ components/   # 여러 화면에서 쓰는 요소
   ├─ api/          # 서버 호출은 여기서만 (목 데이터 전환 포함)
   ├─ mock/         # 시연용 시드 데이터
   ├─ types/        # 백엔드와 주고받는 데이터 모양
   ├─ demo/         # 시연 화면(/demo)과 시연 장치
   └─ styles/       # tokens.css 등
```

## 시연 방식

노트북 한 대에서 `/demo` 페이지를 엽니다. 한 화면에 휴대폰 크기 화면 2개(서로 다른 팀원으로 로그인)와 시연 장치(가짜 시계, 시간 이동, 사용자 바꾸기, 초기화)를 함께 띄웁니다.
