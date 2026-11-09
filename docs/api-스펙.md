## 참고

- 이 명세서는 **기획안과 화면을 기준으로 임의 작성**한 초안입니다. 확정된 스펙이 아닙니다.
- 개발하면서 **수정·삭제·추가 자유롭게** 해 주세요. 대신 바꾼 내용은 **이 페이지에 반영 부탁드립니다!**
- 레인(A/B)도 도메인이 분명한 것 외에는 임의로 나눴습니다. **바꾸셔도 됩니다.**
- 요청·응답 상세는 **Swagger로 공유·확인**합니다.
- 질문이나 의견은 **카톡 또는 이 페이지 댓글로** 주세요.
- **다 갈아엎으셔도 됩니다.** 자유롭게 수정해주세요!
- **11/3 (이진희)**: 디자인 브리프(11/3판)와 어긋나는 줄에 `~~빗금~~`을 쳤습니다. **지우지는 않았습니다** — 뭐가 빠졌는지 보이는 게 나아서요. 네 군데 다 레인 B라 **되살릴지는 장연우님이 정하시면 됩니다.** 되살리려면 빗금만 지우세요.
- **11/7 (이진희)**: BE 작업 상태를 **코드에 맞췄습니다.** `app.openapi()`의 경로와 이 표를 기계로 대조해, 코드에 있는데 "미착수"였던 22개를 "완료"로 고쳤습니다(레인 B 21개 포함 — 장연우님 확인 부탁드립니다). 표에 없던 로그인 두 줄도 더했습니다. FE 작업 상태는 건드리지 않았습니다. `기간 넓혀 다시 조율`은 빗금입니다.
- **11/8 (장연우)**: 레인 B 상태를 코드에 맞췄습니다. 11/7에 완료로 고친 B 21개는 코드와 맞습니다. 받아적기 4줄·에브리타임 2줄·구글 캘린더 3줄을 완료로, 방 만들기·회의록 보기·할 일 직접 추가는 바뀐 칸을 비고에 적었습니다. 받아적기는 엔진과 무관한 API만 완료이고 엔진(무엇으로 받아적을지)은 아직 고르는 중입니다.

## 담당 레인

| 레인 | 맡는 도메인 |
| --- | --- |
| **A** | `Onboard` · `Home` · `Notice` · `Meeting` · `MyPage` 중 시간표·프로필<br>— 온보딩, 홈, 알림, 회의 조율·회의·일정, 내 조건  @이진희 |
| **B** | `Room` · `Record` · `Suggest` · `Task` · `MyPage` 중 외부 연동<br>— 방, 회의록, 할 일 제안, 할 일, 내 조건  @장연우 |
| **공통** | `Demo` (실시간 · 시연 장치) |

## 공통 규칙

### 기본

|  |  |
| --- | --- |
| 베이스 | `/api/v1` |
| 형식 | JSON (UTF-8) |
| 키 | `snake_case` |
| 시각 | ISO 8601 + 오프셋 — `2026-11-10T16:00:00+09:00` |
| 날짜 | `YYYY-MM-DD` / 시각만 필요하면 `HH:mm` |
| ID | 문자열. 프론트는 안을 들여다보지 않음 |
| 반환값 | **서버를 띄우면 `/api/v1/docs`에 전부 있습니다** (OpenAPI). 이 표에 베껴 적지 않습니다 — 코드와 어긋나는 순간 둘 중 어느 쪽이 맞는지 알 수 없어집니다 |

### 권장 규칙

| # | 규칙 | 지키는 쪽 | 안 지키면 |
| --- | --- | --- | --- |
| 1 | 에러 `message`는 화면에 그대로 띄울 한국어 한 줄 | 서버 | 프론트가 문구 매핑 테이블을 엔드포인트 수만큼 만들게 됨 |
| 2 | 시각에 오프셋(`+09:00`)을 붙임 | 서버 | 시연 시계를 옮겼을 때 늦음 판정과 30분 전 알림이 어긋남 |
| 3 | 남의 점수는 응답에 **담지 않음** | 서버 | 실수로 화면에 노출 — 제품의 핵심 약속이 깨짐 |
| 4 | 권한은 서버가 판단해 `can_*`로 내려줌 | 서버·프론트 | 권한 규칙이 바뀔 때마다 프론트를 같이 고쳐야 함 |
| 5 | 목록은 객체로 감쌈 | 서버 | 요약값을 붙일 자리가 없어 응답 모양을 다시 바꾸게 됨 |

### 자주 쓰는 에러 코드

| HTTP | code | 언제 |
| --- | --- | --- |
| 400 | `INVALID_INPUT` | 입력 형식 오류 (`field`로 어느 칸인지) |
| 403 | `FORBIDDEN` | 권한 없음 |
| 403 | `NOT_ASSIGNEE` | 담당자가 아닌 사람이 할 일 상태를 바꾸려 함 |
| 401 | `UNAUTHENTICATED` | 로그인 안 함 |
| 404 | `NOT_FOUND` | 없는 자원 |
| 409 | `ALREADY_CONFIRMED` | 이미 확정된 것을 또 확정 |
| 409 | `ALREADY_RUNNING` | 이미 도는 조율이 있는데 또 시작 |
| 409 | `AWAITING_RESPONSE` | 수락을 기다리는 회의가 있는데 새 조율을 시작. 회의가 끝난 시각이 지나면 풀림 |
| 503 | `AGENT_TIMEOUT` | AI 실패·시간 초과 → 다시 하기 |

### 기술 스택

|  |  |
| --- | --- |
| 프론트 | Vite + React + TypeScript, React Router, dayjs |
| 백엔드 | PostgreSQL + Python + FastAPI |

- 서버 호출은 `frontend/src/api/`에서만. 같은 함수가 목 데이터를 돌려줄 수 있어야 함
- 주고받는 데이터 모양은 `frontend/src/types/`가 기준
- 인증은 세션 쿠키로 갑니다. 다만 시연에서 **한 브라우저에 폰 화면 2개를 서로 다른 팀원으로** 띄워야 하므로, 사용자 바꾸기가 가벼워야 합니다

## 엔드포인트

| 도메인 | 기능명 | method | API Path | 레인 | 우선순위 | 비고 | BE 작업 상태 | FE 작업 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Room | 내 계정 보기 | GET | `/me` | B | High | 방 밖에서도 가능 | **완료** | 미착수 |
| Room | 방 정보·팀원 보기 | GET | `/rooms/{room_id}` | B | High | 팀 화면이 이것 하나로 그려짐. 누적 양보는 단계만 | **완료** | 미착수 |
| Room | 방 만들기 | POST | `/rooms` | B | High | 팀장만. 플랜 없이 바로 생성. 평가 방식(`eval_method`)은 선택(11/4 브리프에서 빠짐) | **완료** | 미착수 |
| Room | 초대 코드로 방 미리보기 | GET | `/rooms/by-invite-code/{code}` | B | Medium |  | **완료** | 미착수 |
| Room | 방 들어가기 | POST | `/rooms/join` | B | High |  | **완료** | 미착수 |
| Onboard | 온보딩 답 해석하기 | POST | `/me/onboarding/interpret` | A | High | AI. 4문항, 1번이 두 값을 냄 | **완료** | 미착수 |
| Onboard | 내 선호 보기 | GET | `/me/preferences` | A | High | 조율이 이 값을 읽음 | **완료** | 미착수 |
| Onboard | 내 선호 고치기 | PATCH | `/me/preferences` | A | High | 보낸 키만 반영 | **완료** | 미착수 |
| Home | 홈 보기 | GET | `/rooms/{room_id}/home` | A | High | 진척률·단계 빠짐 → 디데이만. my_tasks는 B 데이터 | **완료** | 미착수 |
| Notice | 알림 목록 보기 | GET | `/rooms/{room_id}/notifications` | A | High | 3종(늦음·막힘·완료) + 30분 전. 카드는 B가 만듦 | **완료** | 미착수 |
| Notice | 알림 읽음 처리 | POST | `/rooms/{room_id}/notifications/read` | A | Medium | 모두 / 개별 | **완료** | 미착수 |
| Notice | 에이전트가 한 일 보기 | GET | `/rooms/{room_id}/agent-log` | A | Medium | 무엇을·왜·언제. 읽음 처리 없이 쌓임 | 미착수 | 미착수 |
| Notice | 웹 푸시 등록 | PUT | `/me/push-subscription` | A | Low | 팀 전체 빼는 1순위 | 미착수 | 미착수 |
| Notice | 웹 푸시 끄기 | DELETE | `/me/push-subscription` | A | Low | “ | 미착수 | 미착수 |
| Meeting | 조율 시작하기 | POST | `/rooms/{room_id}/schedulings` | A | High | 팀장만. 회의 길이 30분 단위. **11/7**: 수락 대기 회의가 있으면 409 `AWAITING_RESPONSE`. 조율은 뒷단에서 돌고 이 요청은 바로 돌아옴(`status: running`) | **완료** | 미착수 |
| Meeting | 지금까지의 조율 보기 | GET | `/rooms/{room_id}/schedulings/{id}` | A | High | 재진입용. 쌓인 발언을 한 번에. 도는 중이면 다시 부르면 새 발언이 붙어 옴. **11/7**: `meeting_id`(합의·조정이 끝나면 그 회의, 아니면 null) | **완료** | 미착수 |
| Meeting | 조율 발언 받기 | GET | `/rooms/{room_id}/schedulings/{id}/stream` | A | High | SSE. 1.6초마다 하나씩. 스피너 금지. 끝에 `event: done`으로 `status` 전달. **11/7**: 읽기만 함(라운드는 뒷단). `?after=seq`면 그 번호 뒤의 발언만 — 다시 조율할 때 옛 대화를 또 재생하지 않게 | **완료** | 미착수 |
| Meeting | ~~후보 중 팀이 고르기~~ | ~~POST~~ | ~~`/rooms/{room_id}/schedulings/{id}/pick`~~ | A | — | **빗금 11/5**: 사람이 고르는 단계를 없앴습니다. 3라운드 실패·전원 가능한 시간 없음 둘 다 판단 에이전트가 불편·양보 점수로 정하고 **바로 확정**합니다 | 안 만듦 | 안 만듦 |
| Meeting | ~~기간 넓혀 다시 조율~~ | ~~POST~~ | ~~`/rooms/{room_id}/schedulings/{id}/widen`~~ | A | — | **빗금 11/7**: 기간을 서버가 넓혀 주는 길도, 사람이 누르는 버튼도 없앴습니다. 후보가 아예 없으면 조율이 `failed`로 끝나고, 팀장이 **더 넓은 기간으로 조율을 새로 시작**하면 됩니다(`POST /rooms/{room_id}/schedulings`) | 안 만듦 | 안 만듦 |
| Meeting | ~~불참안 받아들이기~~ | ~~POST~~ | ~~`/rooms/{room_id}/schedulings/{id}/accept-absent`~~ | A | — | **빗금 11/5**: `pick`과 같은 이유입니다. 전원 가능한 시간이 없으면 판단 에이전트가 불참안까지 포함해 불편·양보 점수로 정하고 바로 확정하므로, 사람이 "받아들이기"를 누를 자리가 없습니다 | 안 만듦 | 안 만듦 |
| Meeting | ~~거절 뒤 다시 조율~~ | ~~POST~~ | ~~`/rooms/{room_id}/schedulings/{id}/rerun`~~ | A | — | **빗금 11/7**: 따로 안 만들었습니다. **거절하면 `respond`가 그 자리에서 다시 조율합니다** — 라운드 예산(조율 하나에 3)이 남았으면 옛 회의를 `cancelled`로 두고 남은 라운드만 돕니다. 거절한 시간은 그 사람 시간표에 제목 없는 일회성 일정(팀에는 "바쁨")으로 들어갑니다. "이 시간만 / 그날 종일" 선택은 목업·프론트 거절 창에 없어 **이 시간만**입니다. 예산이 0이면 다시 돌지 않고 그 사람을 불참으로 둔 채, 나머지가 모두 수락하면 확정됩니다 | 안 만듦 | 안 만듦 |
| Meeting | 회의 목록 보기 | GET | `/rooms/{room_id}/proposals` | A | Low | **11/5**: `GET /rooms/{room_id}/schedule`이 같은 일을 합니다(조율 중·잡힘·지남 세 묶음). 따로 쓸 화면이 생기면 만듭니다 | 안 만듦 | 안 만듦 |
| Meeting | 회의 보기 | GET | `/rooms/{room_id}/proposals/{id}` | A | High | 차선책 빠짐. 보는 사람마다 내용이 다름 | **완료** | 미착수 |
| Meeting | 수락·거절하기 | POST | `/rooms/{room_id}/proposals/{id}/respond` | A | High | 피드백 한 줄 함께. 전원 수락 시 자동 확정. **조정된 회의(`settled`)는 이미 확정이라 피드백만 받습니다**. **11/7**: 거절하면 예산 안에서 자동으로 다시 조율 — 응답에 `rerun: true`·`rounds_left`, 화면은 조율 화면으로(`?after=`로 새 발언만). 다시 도는 동안 옛 회의에 답하면 409 `CLOSED` | **완료** | 미착수 |
| Meeting | 선호 변경 되돌리기 | POST | `/me/preference-changes/{id}/undo` | A | Medium | 말없이 바꾸면 안 되므로 필요. **11/5**: 피드백 한 줄을 `meeting_response.feedback`에 저장만 하고 선호를 자동으로 바꾸지 않으므로 되돌릴 것이 아직 없습니다. 자동 반영을 넣을 때 같이 만듭니다 | 미착수 | 미착수 |
| Meeting | 일정 보기(회의 관리) | GET | `/rooms/{room_id}/schedule` | A | High | 회의 관리로 바뀜 (전 timeline). 조율 중도 자리 잡음 | **완료** | 미착수 |
| Record | 회의록 목록 보기 | GET | `/rooms/{room_id}/meetings` | B | High | 주제 한 줄이 보여야 나중에 찾음 | **완료** | 미착수 |
| Record | 회의 기록 시작하기 | POST | `/rooms/{room_id}/meetings` | B | High | 확정된 회의 없이도 됨 | **완료** | 미착수 |
| Record | 회의록 보기 | GET | `/rooms/{room_id}/meetings/{id}` | B | High | 원문 + 요약 + 그 회의에서 확정된 할 일 + 회의에서 끝난 일(`done_tasks`). 받아적기 상태(`recording_state`), 줄마다 목소리 라벨(`speaker_label`) | **완료** | 미착수 |
| Record | 직접 쓰기 | PUT | `/rooms/{room_id}/meetings/{id}/transcript` | B | High | 보조 경로지만 가장 먼저 만듦 (AI 없이 도는 길). 남는 줄이 없는 글은 400(원문 그대로). 받아적는 중이어도 받아적은 글이 없으면 직접 쓰기로 바뀜 | **완료** | 미착수 |
| Record | 요약·할 일 뽑기 | POST | `/rooms/{room_id}/meetings/{id}/summarize` | B | High | AI. 네 묶음을 한 호출로 | **완료** | 미착수 |
| Record | 받아적기 시작 | POST | `/rooms/{room_id}/meetings/{id}/recording/start` | B | High | ~~동의 고려 필요성~~ → 브리프 11/3 "참석자 동의 없앰. 브라우저 마이크 권한만 최초 1회". **엔드포인트는 그대로 필요합니다.** 받아적는 중 다시 눌러도 그대로. 직접 쓴 원문이 있으면 409, 멈춘 뒤 다시 시작 불가 | **완료** | 미착수 |
| Record | 받아적은 글 올리기 | POST | `/rooms/{room_id}/meetings/{id}/transcript/segments` | B | High | 끊겼다 다시 올려도 중복·누락 없게. 번호·목소리 라벨·글자를 50줄까지, 같은 번호는 건너뜀, 응답에 빠진 번호 | **완료** | 미착수 |
| Record | 받아적기 정지 | POST | `/rooms/{room_id}/meetings/{id}/recording/stop` | B | High | 원문을 먼저 저장하고 요약은 따로. 두 번 눌러도 그대로. 받아적는 중에는 요약이 409, 직접 쓰기는 받아적은 글이 있을 때만 409 | **완료** | 미착수 |
| Record | 받아적기 녹음 올리기 | POST | `/rooms/{room_id}/meetings/{id}/recording/audio` | B | High | 멈출 때 녹음 파일을 본문에 그대로(30분·25MB). AI(Gemini)가 받아적어 줄·목소리 라벨(A·B…)로 쌓고 멈춤. 녹음은 저장 안 함. 실패해도 받아적는 중 그대로라 다시 올리면 됨 | **완료** | 미착수 |
| Record | 말한 사람 확인 | PUT | `/rooms/{room_id}/meetings/{id}/speaker-mapping` | B | Medium | ~~목소리 A~D → 사람.~~ → 브리프 "자동 화자 구분 없음. **받아적는 사람이 고릅니다**". 자동 화자 구분은 STT 서비스를 고르는 문제라 공짜가 아닙니다. 한 번에 전체 반영은 그대로. 목소리 라벨 → 팀원 한 번에 + 줄마다 고치기(우선), null은 모름 | **완료** | 미착수 |
| Suggest | 제안 확정하기 | POST | `/rooms/{room_id}/suggestions/confirm` | B | High | 한꺼번에 확정 필수. 담당자 없이도 확정됨 | **완료** | 미착수 |
| Suggest | 제안 고치기 | PATCH | `/rooms/{room_id}/suggestions/{id}` | B | High | 제목·담당자·기한 (예상 시간 빠짐). 확정 전에만 | **완료** | 미착수 |
| Suggest | 제안 버리기 | DELETE | `/rooms/{room_id}/suggestions/{id}` | B | High | 되돌릴 수 없어 한 번 더 물음 | **완료** | 미착수 |
| Suggest | ~~끝난 일 되돌리기~~ | ~~POST~~ | ~~`/rooms/{room_id}/auto-completed/{id}/undo`~~ | B | — | **빗금 11/3**: 되돌릴 게 있다는 건 시스템이 스스로 완료로 바꾼다는 뜻인데, 브리프의 알림 3종에 그 판정이 없습니다("완료"는 **사람이 바꾼 것**을 알리는 카드). 자동 판정을 둘 거면 `task`에 열이 더 붙습니다. 장연우님 확인 | 보류 | 보류 |
| Suggest | ~~필요 없는 일 유지하기~~ | ~~POST~~ | ~~`/rooms/{room_id}/unneeded/{id}/keep`~~ | B | — | **빗금 11/3**: 위와 같음. 자동 "필요 없음" 판정이 브리프에 없습니다. "필요 없음"은 사람이 직접 빼는 것뿐입니다. 장연우님 확인 | 보류 | 보류 |
| Task | 팀 할 일 보기 | GET | `/rooms/{room_id}/tasks` | B | High | task_counts(개수)로 바뀜. 담당자 없음 묶음이 맨 위 | **완료** | 미착수 |
| Task | 내 할 일 보기 | GET | `/rooms/{room_id}/tasks/mine` | B | High | 기한 순. 확정된 것만 | **완료** | 미착수 |
| Task | 할 일 하나 보기 | GET | `/rooms/{room_id}/tasks/{id}` | B | Medium | 고치기 화면용 | **완료** | 미착수 |
| Task | 할 일 상태 바꾸기 | PATCH | `/rooms/{room_id}/tasks/{id}/status` | B | High | 담당자만. 막힘을 고르면 팀에 바로 알림 | **완료** | 미착수 |
| Task | 할 일 내용 고치기 | PATCH | `/rooms/{room_id}/tasks/{id}` | B | High | 전원. 제목·담당자·기한 | **완료** | 미착수 |
| Task | 할 일 빼기 ("필요 없음") | POST | `/rooms/{room_id}/tasks/{id}/dismiss` | B | High | 전원. "삭제"라고 쓰지 않음 | **완료** | 미착수 |
| Task | 할 일 직접 추가 | POST | `/rooms/{room_id}/tasks` | B | High | AI 없이 도는 길이라 High. 회의록에서 추가하면 `meeting_id`로 출처 회의 | **완료** | 미착수 |
| Task | 담당자 넘기기 | POST | `/rooms/{room_id}/tasks/{id}/reassign` | B | Medium | 할일 내용 고치기랑 병합 가능 | **완료** | 미착수 |
| MyPage | 내 프로필 보기 | GET | `/rooms/{room_id}/me/profile` | A | Medium | 누적 양보 단계·회의별 양보 기록 | 미착수 | 미착수 |
| MyPage | 주간 시간표 보기 | GET | `/rooms/{room_id}/me/schedule` | A | Medium | 수업·알바·약속·팀 회의 구분 | 미착수 | 미착수 |
| MyPage | 일정 직접 추가 | POST | `/me/schedule/items` | A | Medium | 요일 여러 개를 한 번에 | 미착수 | 미착수 |
| MyPage | 일정 지우기 | DELETE | `/me/schedule/items/{id}` | A | Medium |  | 미착수 | 미착수 |
| MyPage | 묶인 일정 고치기 | PUT | `/me/schedule/groups/{id}` | A | Low | 요일마다 다른 시간 | 미착수 | 미착수 |
| MyPage | 묶인 일정 지우기 | DELETE | `/me/schedule/groups/{id}` | A | Low |  | 미착수 | 미착수 |
| MyPage | 에브리타임 연결 | POST | `/me/integrations/everytime` | B | Low | 링크 붙여넣기. 사람 확인 단계 없음. 다시 보내면 다시 불러오기. 약 11초 | **완료** | 미착수 |
| MyPage | 에브리타임 끊기 | DELETE | `/me/integrations/everytime` | B | Low | 에브리타임 수업만 지움 | **완료** | 미착수 |
| MyPage | 구글 캘린더 연결 | POST | `/me/integrations/google-calendar` | B | Low | 읽기 권한만. 팀 전체 빼는 2순위. 약속은 제목 없이 "바쁨" | **완료** | 미착수 |
| MyPage | 구글 캘린더 끊기 | DELETE | `/me/integrations/google-calendar` | B | Low | “ | **완료** | 미착수 |
| MyPage | 구글 캘린더 동기화 | POST | `/me/integrations/google-calendar/sync` | B | Low | “ | **완료** | 미착수 |
| Demo | 실시간 변경 받기 | GET | `/rooms/{room_id}/events` | 공통 | High | SSE. 한쪽 수락 → 다른 쪽 즉시 반영 | 미착수 | 미착수 |
| Demo | 사용자 바꾸기 | POST | `/demo/switch-user` | 공통 | High | 시연 필수 | 미착수 | 미착수 |
| Demo | 시연 시계 보기 | GET | `/demo/clock` | 공통 | High | 새로고침해도 어디 가 있는지 알아야 함 | 미착수 | 미착수 |
| Demo | 시연 시계 옮기기 | PUT | `/demo/clock` | 공통 | High | 모든 판정의 기준 시각 | 미착수 | 미착수 |
| Demo | 실제 시각으로 되돌리기 | DELETE | `/demo/clock` | 공통 | Medium |  | 미착수 | 미착수 |
| Demo | 시드로 초기화 | POST | `/demo/reset` | 공통 | High | 시연 중 다시 돌릴 때 | 미착수 | 미착수 |
| 공통 | 로그인하기 | POST | `/sessions` | 공통 | High | 이름만 보내면 그 사람이 됨. **비밀번호는 아직 없음**(시연 4명용). 서명 쿠키로 유지 | **완료** | 미착수 |
| 공통 | 로그아웃하기 | DELETE | `/sessions` | 공통 | High |  | **완료** | 미착수 |
