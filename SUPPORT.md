# 지원 및 개발 환경 가이드 (Support & Setup)

프로젝트의 개발 환경 설정 및 문제 해결 가이드입니다.

---

## 1. 개발 환경 및 요구 사양

| 영역 | 환경 |
| :--- | :--- |
| 프론트엔드 (`frontend/`) | React + TypeScript (Vite), Node.js 24 LTS |
| 백엔드 (`backend/`) | (스택 확정 후 기입) |
| 시연 | 배포한 서버에 노트북(팀장)·휴대폰(팀원)으로 각각 로그인 |

---

## 2. 실행 방법

### 프론트엔드
```bash
cd frontend
npm install
npm run dev
```
- 백엔드(`localhost:8000`)를 먼저 띄웁니다. 개발 서버가 `/api`를 백엔드로 넘깁니다. 서버 주소(`VITE_API_URL`)는 [`frontend/README.md`](frontend/README.md)를 봅니다.
- 시연 당일에는 개발 서버 대신 빌드본으로 띄웁니다: `npm run build` 후 `npm run preview`

### 백엔드
- (스택 확정 후 기입)

---

## 3. 환경 변수

- 비밀정보가 필요한 경우 `.env.example`을 복사해 `.env`를 만들고 값을 채웁니다. `.env`는 커밋하지 않습니다.
- AI API 키는 백엔드 `.env`에만 둡니다.

---

## 4. 자주 묻는 질문 (FAQ) & 트러블슈팅

- (작업하며 추가)

---

## 5. 도움 및 지원 요청 채널

- **버그 제보 및 기능 제안**: GitHub 저장소의 [Issues](../../issues) 탭을 통해 등록해 주세요.
