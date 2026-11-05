# 팀플 에이전트

> **제15회 컴퓨터학과 소프트웨어 경진대회(2026) 출품작**  
> 팀원마다 붙는 AI 에이전트가 서로 양보하며 회의 시간을 잡고, 회의에서 정한 일을 할 일로 만들고, 마감까지 무엇이 막혔는지 먼저 알려 주는 대학생 팀 프로젝트 도우미

---

## 📌 프로젝트 정보

- **대회**: 제15회 소프트웨어 경진대회 (2026-11-19)
- **형태**: 휴대폰 크기 웹앱 (시연은 노트북 브라우저)
- **기술 스택**: 프론트엔드 React + TypeScript (Vite) · 백엔드 PostgreSQL + Python + FastAPI
- **팀 구성**: 프론트엔드 1명, 백엔드 2명

---

## ✨ 핵심 기능

| 기능 | 설명 |
| :--- | :--- |
| **회의 시간 조율** | 팀원별 에이전트가 각자의 일정을 말하고, 중립 판단 에이전트가 정리해 회의안을 냅니다. 누가 맞춰 줬는지가 양보 기록으로 쌓여 다음 조율에 반영됩니다. |
| **회의록 → 할 일** | 회의록을 붙여 넣으면 결정·논의·보류로 요약하고, 할 일을 "AI 제안"으로 바로 등록합니다. 사람이 고치거나 확정합니다. |
| **알림** | 늦음, 막힘, 완료를 감지해 알림함에 이유와 함께 보여 줍니다. 회의 30분 전에도 알려 줍니다. |

---

## 🗂️ 폴더 구조

```text
School_2602SWC/
├─ frontend/   # React + TypeScript 웹앱 (화면, 시연용 목 데이터, 시연 화면)
├─ backend/    # API 서버·에이전트 로직 (PostgreSQL + FastAPI + SQLModel)
├─ docs/       # DB 설계·API 스펙·디자인 브리프·화면 목업(mockup/)
└─ .github/    # 이슈·PR·커밋 템플릿
```

---

## 🚀 빠른 시작 (Quick Start)

1. 저장소 클론:
   ```bash
   git clone https://github.com/leechimins/School_2602SWC.git
   ```
2. 백엔드 실행: [`backend/README.md`](backend/README.md) — Docker로 Postgres를 띄우고 네 줄이면 됩니다.
3. 프론트엔드 실행: `frontend/`가 생기면 [`frontend/README.md`](frontend/README.md)에 적습니다.

---

## 📚 프로젝트 문서

| 문서 | 설명 |
| :--- | :--- |
| **[CONTRIBUTING.md](CONTRIBUTING.md)** | **기여 가이드**: 브랜치·커밋·PR 규칙, 코드 컨벤션, 화면 용어와 표시 규칙 |
| **[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)** | **협업 수칙**: 작업 전후 동기화, 프론트·백엔드 역할 분담 |
| **[SUPPORT.md](SUPPORT.md)** | **개발 환경 및 지원**: 실행 방법, 환경 변수, FAQ |
| **[docs/api-스펙.md](docs/api-스펙.md)** | **API 스펙**: 엔드포인트 목록, 공통 규칙, 레인 분담 |
| **[docs/디자인-브리프.md](docs/디자인-브리프.md)** | **디자인 브리프**: 화면별로 무엇이 들어가는지 |
| **[docs/mockup/index.html](docs/mockup/index.html)** | **화면 목업**: 브라우저로 바로 여는 단일 HTML. 왼쪽 시연 장치로 화면 상태를 바꿔 봅니다 |
| **[backend/db-설계.md](backend/db-설계.md)** | **DB 설계**: 테이블 22개, ERD, 접점 세 곳 |
