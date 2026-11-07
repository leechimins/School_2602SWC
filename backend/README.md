# backend

API 서버와 에이전트(회의 시간 조율, 회의록 요약, 할 일 추출) 로직.

- **스택**: PostgreSQL 16 + Python 3.13 + FastAPI + SQLModel
- **설계 문서**: [`db-설계.md`](db-설계.md) · [`../docs/api-스펙.md`](../docs/api-스펙.md) · [`../docs/디자인-브리프.md`](../docs/디자인-브리프.md)

---

## 지금 무엇이 들어 있나

**테이블 17개 + 시연 시드 + 온보딩 + 조율의 계산 부분까지입니다.** 에이전트가 말을 하는 라운드는 LLM 공급자를 고른 뒤입니다.

### 도는 엔드포인트

| method | path | 하는 일 |
|---|---|---|
| GET | `/api/v1/health` | DB가 붙는지까지 같이 봅니다 |
| POST | `/api/v1/sessions` | **로그인.** 이름을 보내면 그 사람이 됩니다 |
| DELETE | `/api/v1/sessions` | 로그아웃 |
| POST | `/api/v1/me/onboarding/interpret` | 온보딩 네 답을 받아 **저장**하고 저장된 값을 돌려줍니다 |
| GET | `/api/v1/me/preferences` | 내 조건 화면과 조율이 읽습니다 |
| PATCH | `/api/v1/me/preferences` | 내 조건 화면의 편집. **보낸 키만** 반영 |
| POST | `/api/v1/rooms/{room_id}/schedulings` | **조율 시작.** 팀장만. 후보와 사람별 불편 점수까지 만듭니다 |
| GET | `/api/v1/rooms/{room_id}/schedulings/{id}` | 지금까지의 조율. 재진입용 |

`http://localhost:8000/api/v1/docs`에서 다 눌러 볼 수 있습니다. **코드를 처음 읽으면 [`코드-안내.md`](코드-안내.md)부터 보세요** — 파일을 읽는 순서, 요청 하나가 흐르는 길, 정한 것과 그 이유, 다음에 할 것이 적혀 있습니다.

**로그인은 아직 비밀번호가 없습니다.** 이름을 보내면 그 사람이 됩니다 — 인증이 아니라 사용자 선택입니다. Room 도메인이라 원래 레인 B 것인데 `/me/*`가 사용자 없이는 아예 돌지 않아서 A가 먼저 깔았습니다. `user` 테이블은 건드리지 않았고, 비밀번호를 붙일 자리는 `app/shared/auth.py`의 `login()` 안에 주석으로 적어 뒀습니다.

**에러 모양이 명세에 맞춰져 있습니다.** `main.py`의 예외 처리기 둘이 FastAPI 기본값(`{"detail": ...}`, 검사 실패는 422)을 `{"code", "field", "message"}` + 400으로 바꿉니다. `message`는 화면에 그대로 띄울 한국어 한 줄입니다.

| 폴더 | 테이블 | 담당 |
|---|---|---|
| `app/shared/models.py` | `user` · `room` · `membership` | **Room 도메인 — 레인 B 것.** A의 테이블이 전부 이 셋으로 FK가 걸려서 A가 먼저 만들어 뒀습니다. 열을 더하거나 고칠 때 A에게 안 물어봐도 됩니다 |
| `app/me/models.py` | `preference` · `schedule_item` | Onboard · MyPage 시간표 |
| `app/meeting/models.py` | `scheduling` · `candidate_slot` · `slot_cost` · `utterance` · `meeting` · `meeting_response` · `yield_entry` · `preference_change` | Meeting |
| `app/notice/models.py` | `notification` · `agent_log` · `push_subscription` | Notice |
| `app/demo/models.py` | `demo_state` | 시연 시계 (공통) |

레인 B가 올릴 것 5개(`calendar_link` · `transcript_segment` · `minutes` · `minutes_item` · `task`)는 아직 없습니다. 설계는 `db-설계.md`에 있습니다.

**A가 B의 테이블에서 읽는 것은 셋뿐입니다** — `user.id`, `room.leader_user_id`(팀장인지 확인), `membership.yield_total`(조율의 양보 차등). 이 셋을 바꿀 때만 서로 알려 주면 됩니다.

### 다음에 올 것이 들어갈 자리

에이전트 로직은 **도메인 폴더 안**에 둡니다. 라운드 루프는 `candidate_slot`·`slot_cost`·`yield_total`을 읽어야 돌아가므로 `app/meeting/` 밖에서는 의미가 없습니다.

딱 하나, **모델 호출은 빼냅니다** → `app/shared/llm.py`. 키·타임아웃·재시도·구조화 출력 검증·LLM 끄기 스위치가 여기 모입니다. 회의록 쪽도 같은 것을 쓰고, 두 번 짜면 `503 AGENT_TIMEOUT`을 두 군데서 다르게 처리하게 됩니다.

```
app/shared/llm.py          모델 호출 한 군데
app/meeting/
  slots.py                 빈칸 찾기      ← AI 아님. 순수 계산
  scorer.py                불편 점수·총점  ← AI 아님. 순수 계산
  agent_loop.py            라운드 돌리기   ← AI
  prompts.py               발언 프롬프트
  feedback.py              피드백 → 선호 반영 ← AI
  service.py               조율 한 번의 순서 (db-설계.md §6)
  router.py                /schedulings · /proposals
```

**계산과 AI를 파일로 가르는 게 요점입니다.** `slots.py`·`scorer.py`가 숫자를 정하고 `agent_loop.py`는 그 결과를 말로 설명할 뿐입니다. 섞으면 "이 점수 누가 정했냐"가 흐려지고, 리허설과 본 시연이 같은 답을 낸다는 보장이 무너집니다.

---

## Postgres를 처음 쓴다면

**SQLite와 다른 점은 딱 하나입니다. 파일이 아니라 서버입니다.**

| | SQLite | Postgres |
|---|---|---|
| 형태 | `app.db` 파일 하나 | 돌아가는 서버 프로그램 |
| 쓰려면 | 파일을 열면 됨 | **켜 두고** 주소로 접속 |
| 접속 주소 | 파일 경로 | `localhost:5432` + 아이디·비번·DB 이름 |
| 껐을 때 | 그냥 파일 | 접속 실패 (`connection refused`) |

그래서 할 일이 하나 늘어납니다. **서버를 켜 두는 것.** Docker가 그걸 대신해 줍니다 — 직접 설치할 건 없습니다.

Docker는 **빈 Postgres 서버**를 띄워 줍니다. 우리 설계가 들어 있는 게 아닙니다. 테이블은 파이썬 코드가 만듭니다.

| 층 | 무엇 | 어디 |
|---|---|---|
| 1. 합의 | 사람이 읽고 고치는 설계 | `db-설계.md` |
| 2. 코드 | **클래스 하나 = 테이블 하나** | `app/*/models.py` |
| 3. 실제 | 코드를 보고 SQL을 서버에 보냄 | `python -m tools.reset_db` |

`.sql` 파일을 손으로 써서 넣는 방식도 있지만 쓰지 않습니다. 클래스가 **하나의 진실**이어야 문서·코드·DB가 어긋나지 않습니다.

---

## 처음 한 번

Docker Desktop을 켜 두고(고래 아이콘이 초록색) 순서대로 칩니다.

```bash
cd backend
docker compose up -d
pip install -r requirements.txt
cp .env.example .env
python -m tools.reset_db
```

확인:

```bash
pytest -q
uvicorn app.main:app --reload
```

`http://localhost:8000/api/v1/docs`에 Swagger가 열립니다. `GET /api/v1/health`가 `{"status":"ok","db":"ok"}`면 다 붙은 것입니다.

## 매일

```bash
docker compose up -d          # 노트북을 켤 때 한 번 (이미 떠 있으면 아무 일 없음)
uvicorn app.main:app --reload
```

---

## 자주 쓰는 것

### DB 안을 들여다보기

```bash
docker compose exec db psql -U teamagent -d teamagent
```

`psql`에 들어가면 쓰는 명령입니다. SQL이 아니라 `\`로 시작하는 psql 전용 명령입니다.

| 명령 | 하는 일 |
|---|---|
| `\dt` | 테이블 목록 |
| `\d membership` | 그 테이블의 열과 제약 |
| `\di` | 인덱스 목록 |
| `\q` | 나가기 |

행을 보려면 SQL을 칩니다. 끝에 **세미콜론**이 있어야 실행됩니다.

```sql
SELECT name FROM "user";
SELECT * FROM membership;
```

> `user`는 Postgres 예약어라서 `FROM "user"`처럼 **따옴표**가 필요합니다. 파이썬 코드에서는 SQLAlchemy가 알아서 붙여 줍니다.

### 스키마를 고쳤을 때

마이그레이션 도구를 쓰지 않습니다. 모델을 고쳤으면 지우고 다시 만듭니다.

```bash
python -m tools.reset_db
```

이건 테이블을 하나씩 지우는 게 아니라 **스키마를 통째로** 지웁니다(`DROP SCHEMA public CASCADE`). 그래서 **모델에서 테이블을 뺐을 때도** 막히지 않습니다 — 하나씩 지우는 방식은 모델에 없는 테이블을 모르고 넘어가서, 남은 테이블의 FK가 다음 `DROP`을 막습니다.

**다만 배포 DB에 사람이 넣은 데이터가 생긴 뒤부터는 이걸 쓸 수 없습니다.** 그때부터는 손으로 `ALTER TABLE`을 씁니다.

### 리허설 사이에 시드로 되돌리기

셸을 열 수 있으면 위의 `python -m tools.reset_db`. 배포 서버처럼 셸이 없으면 HTTP로 합니다.

```bash
curl -X POST https://<서버>/api/v1/demo/reset -H "X-Demo-Key: <DEMO_RESET_KEY 값>"
```

- 서버 환경변수 `DEMO_RESET_KEY`가 있어야 켜집니다. 없거나 헤더가 틀리면 403입니다 — 시연 주소는 관객 폰에도 열리기 때문입니다. 열쇠는 ASCII로 정합니다.
- 테이블은 그대로 두고 행만 비운 뒤 시드를 다시 넣습니다(시연 시계도 실제 시각으로). 204면 끝입니다.
- 열린 조율 화면이 DB를 붙잡고 있으면 5초 기다리다 409 `BUSY`이고 아무것도 안 지워집니다. 그 화면을 닫고 다시 부릅니다.
- 폰들은 다시 로그인하지 않아도 됩니다. 사람 번호가 시드 순서대로 같게 다시 매겨져 쿠키가 같은 사람을 가리킵니다.
- 스키마를 고친 뒤라면 이게 아니라 `tools.reset_db`입니다.

### 완전히 처음부터

```bash
docker compose down -v
docker compose up -d
python -m tools.reset_db
```

`-v`가 볼륨까지 지웁니다. 이게 없으면 데이터가 남습니다.

---

## 막혔을 때

| 증상 | 원인과 조치 |
|---|---|
| `failed to connect to the docker API` | Docker Desktop이 꺼져 있습니다. 켜고 고래 아이콘이 초록색이 될 때까지 기다립니다 |
| `connection refused` (5432) | 컨테이너가 안 떠 있습니다. `docker compose ps`로 보고 `up -d` |
| `port is already allocated` | 5432를 이미 다른 Postgres가 쓰고 있습니다. `docker-compose.yml`의 `"5432:5432"`를 `"5433:5432"`로 바꾸고 `.env`의 포트도 같이 바꿉니다 |
| `DATABASE_URL이 없습니다` | `.env`가 없습니다. `cp .env.example .env` |
| `relation "..." does not exist` | 테이블이 없습니다. `python -m tools.reset_db` |
| 테스트만 실패 | `teamagent_test` DB가 없습니다. 볼륨을 만들 때 한 번만 생기므로 `docker compose down -v` 후 다시 띄웁니다 |

---

## 폴더

```
backend/
  app/
    main.py              FastAPI 앱, 쿠키 서명, 에러 모양
    shared/              둘이 같이 읽는 것
      base.py            시각 다루는 규칙, 열 만드는 도우미
      enums.py           열거값 전부
      db.py              접속, 테이블 생성, reset_schema, 세션 의존성
      auth.py            로그인·로그아웃, current_user_id
      demo_clock.py      시연 시계 — "지금"은 전부 여기서 읽는다
      models.py          user · room · membership  ← 레인 B 것
    me/
      models.py          preference · schedule_item
      schemas.py         입력·출력 모델 (table=True가 없는 것들)
      router.py          온보딩·내 조건 엔드포인트
    meeting/
      models.py          조율 8개
      slots.py           빈칸 찾기      ← AI 아님. 순수 계산
      scorer.py          불편 점수·순서  ← AI 아님. 순수 계산
      service.py         조율 한 번의 순서 (db-설계.md §6)
      schemas.py         입력·출력 모델
      router.py          /schedulings
    notice/models.py     알림 3개
    demo/models.py       demo_state
  tools/
    seed.py              시연 데이터
    reset_db.py          지우고 만들고 시드
  tests/
    test_models.py       제약이 실제로 물리는지
    test_seed.py         시드가 시연 전제를 만족하는지
    test_schemas.py      시각 피커가 분으로 바뀌는지 (DB 없이)
    test_slots.py        빈칸 찾기와 채점 (DB 없이)
    test_me_api.py       온보딩을 실제 요청으로 끝까지
    test_scheduling_api.py  조율 시작·조회
  db-설계.md             테이블 22개 설계 (레인 B 것 포함)
  코드-안내.md           처음 읽을 때. 읽는 순서와 정한 것들
```

---

## 코드를 쓸 때 지킬 것 셋

1. **`datetime.now()`와 SQL `NOW()`를 쓰지 않습니다.** 판정에 쓰는 "지금"은 `shared.demo_clock.now(session)`에서 읽습니다. 시연에서 날짜를 옮겨야 하기 때문입니다.
2. **naive `datetime`을 만들지 않습니다.** 전부 `+09:00`이 붙은 aware입니다. 명세의 권장 규칙 2이고, 안 지키면 늦음 판정과 30분 전 알림이 조용히 어긋납니다.
3. **입력 검사를 모델 클래스에 기대지 않습니다.** SQLModel은 `table=True`인 클래스에서 Pydantic 검사를 끕니다 — 이상한 값을 넣어도 파이썬에서는 안 막힙니다. 그래서 DB의 `CHECK` 제약이 진짜 방어선이고, 라우터에서는 `table=True`가 없는 입력용 클래스를 따로 두고 받습니다.

---

## 프론트와의 약속

- 주고받는 데이터 모양은 `frontend/src/types/`의 타입을 기준으로 맞추고, 바꿀 때는 PR로 서로 확인합니다.
- 프론트는 서버가 없거나 실패해도 같은 모양의 목 데이터로 화면을 이어 갑니다.
- API 베이스는 `/api/v1`, 키는 `snake_case`, 시각에는 오프셋(`+09:00`)을 붙여 보냅니다.
- 남의 불편 점수는 응답에 담지 않습니다. 본인 것만 숫자로 내려가고, 남은 괜찮음/조금/많이로 바꿔 보냅니다.
