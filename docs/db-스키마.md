# DB 스키마 ERD

- 기준: 코드 `backend/app/*/models.py` (2026-11-04). 다르면 코드가 맞습니다.
- 22개 테이블을 도메인별 3장으로 나눠 그렸습니다. 다른 장의 테이블은 연결선에만 나옵니다.
- 설계 이유와 조율 흐름은 [backend/db-설계.md](../backend/db-설계.md).
- 점수 범위처럼 아직 안 정해진 값과 팀 합의 전인 항목은 뺐습니다.
- 표기: `nullable`은 비어도 되는 열, 따옴표 안은 열거값이나 메모입니다. `datetime`은 전부 `TIMESTAMPTZ`(+09:00).

## 1. Room · 온보딩 · 시간표 · 연동 · 시연

```mermaid
erDiagram
    user ||--o| preference : "1:1"
    user ||--o{ schedule_item : ""
    user ||--o{ calendar_link : ""
    user ||--o{ membership : ""
    room ||--o{ membership : ""
    user ||--o{ room : "팀장"

    user {
        int id PK
        string name
        datetime created_at
    }

    room {
        int id PK
        string name
        string description
        date start_date
        date due_date "마감 디데이 기준"
        string eval_method
        int member_count
        string invite_code UK
        int leader_user_id FK "팀장은 여기서만 봄"
        datetime created_at
    }

    membership {
        int id PK
        int room_id FK
        int user_id FK
        string part "nullable"
        int yield_total "누적 양보, A가 씀"
        datetime joined_at
    }

    preference {
        int id PK
        int user_id FK, UK
        int day_start_min "nullable"
        int day_end_min "nullable"
        string mode_pref "nullable, offline / online / any"
        string dayparts "nullable, text[]"
        string avoid_raw "nullable"
        string avoid_polished "nullable"
        datetime updated_at
    }

    schedule_item {
        int id PK
        int user_id FK
        int group_id "nullable"
        string source "everytime / google / manual"
        string kind "class / parttime / appointment"
        string title "nullable"
        string recurrence "weekly / once"
        int weekday "nullable, 0=월"
        int start_min "nullable"
        int end_min "nullable"
        date valid_from "nullable"
        date valid_to "nullable"
        datetime start_at "nullable"
        datetime end_at "nullable"
        datetime created_at
    }

    calendar_link {
        int id PK
        int user_id FK
        string kind "everytime / google"
        string external_ref
        string access_token "nullable"
        string refresh_token "nullable"
        string status "ok / failed"
        datetime last_synced_at "nullable"
        datetime created_at
    }

    demo_state {
        int id PK "항상 1"
        datetime now_at "nullable, 시연 시계"
        datetime updated_at
    }
```

- `membership (room_id, user_id)` 유일, `calendar_link (user_id, kind)` 유일.
- `demo_state`는 한 행만 있는 테이블이라 연결선이 없습니다.

## 2. 조율 · 회의

```mermaid
erDiagram
    room ||--o{ scheduling : ""
    user ||--o{ scheduling : "시작한 팀장"
    scheduling ||--o{ candidate_slot : ""
    scheduling ||--o{ utterance : ""
    candidate_slot ||--o{ slot_cost : ""
    user ||--o{ slot_cost : ""
    user |o--o{ utterance : "member일 때만"
    scheduling |o--o{ meeting : "조율 없이도 가능"
    candidate_slot |o--o{ meeting : ""
    room ||--o{ meeting : ""
    meeting ||--o{ meeting_response : ""
    user ||--o{ meeting_response : ""
    meeting ||--o{ yield_entry : ""
    room ||--o{ yield_entry : ""
    user ||--o{ yield_entry : ""
    meeting |o--o{ preference_change : ""
    user ||--o{ preference_change : ""

    scheduling {
        int id PK
        int room_id FK
        int started_by FK
        string topic
        datetime window_start
        datetime window_end
        int duration_min "30의 배수"
        string mode "offline / online / any"
        string status "running / agreed / needs_pick / no_common / failed"
        int rounds_used "0~3"
        datetime created_at
        datetime closed_at "nullable"
    }

    candidate_slot {
        int id PK
        int scheduling_id FK
        datetime start_at
        datetime end_at
        float total_cost
        int round_no "1~3"
        bool proposed
        int absentee_user_id FK "nullable"
        datetime created_at
    }

    slot_cost {
        int id PK
        int candidate_slot_id FK
        int user_id FK
        int score "본인에게만 숫자로 보임"
        bool available
        string reason
    }

    utterance {
        int id PK
        int scheduling_id FK
        int round_no "1~3"
        int seq
        string speaker_kind "judge / member"
        int speaker_user_id FK "nullable"
        string text
        datetime created_at
    }

    meeting {
        int id PK
        int room_id FK
        int scheduling_id FK "nullable"
        int candidate_slot_id FK "nullable"
        string topic
        datetime start_at
        datetime end_at
        string mode "offline / online"
        string status "proposed / confirmed / done / cancelled"
        string rationale
        datetime confirmed_at "nullable"
        string transcript_mode "nullable, stt / manual, B가 씀"
        datetime recording_started_at "nullable, B가 씀"
        datetime recording_stopped_at "nullable, B가 씀"
        datetime created_at
    }

    meeting_response {
        int id PK
        int meeting_id FK
        int user_id FK
        string state "pending / accepted / declined"
        string feedback "nullable"
        datetime responded_at "nullable"
    }

    yield_entry {
        int id PK
        int room_id FK
        int meeting_id FK
        int user_id FK
        int points
        int discomfort
        string reason
        datetime created_at
    }

    preference_change {
        int id PK
        int user_id FK
        int meeting_id FK "nullable"
        string source_text
        string field
        string before "nullable"
        string after "nullable"
        string summary
        bool reverted
        datetime created_at
    }
```

- 유일: `slot_cost (candidate_slot_id, user_id)` · `utterance (scheduling_id, seq)` · `meeting_response (meeting_id, user_id)` · `yield_entry (meeting_id, user_id)`.
- `scheduling`은 한 방에 `status='running'`이 하나만 있을 수 있습니다 (부분 유일 인덱스).
- `proposed` 상태의 `meeting`이 곧 "회의안"입니다. 별도 테이블은 없습니다.

## 3. 회의록 · 할 일 · 알림

```mermaid
erDiagram
    meeting ||--o{ transcript_segment : ""
    user |o--o{ transcript_segment : "말한 사람"
    meeting ||--o| minutes : ""
    minutes ||--o{ minutes_item : ""
    room ||--o{ task : ""
    meeting |o--o{ task : "출처 회의"
    meeting |o--o{ task : "끝난 회의"
    user |o--o{ task : "담당자"
    user |o--o{ task : "확정한 사람"
    task |o--o{ notification : ""
    meeting |o--o{ notification : ""
    room ||--o{ notification : ""
    user ||--o{ notification : "받는 사람"
    room ||--o{ agent_log : ""
    user |o--o{ agent_log : ""
    user ||--o{ push_subscription : ""

    transcript_segment {
        int id PK
        int meeting_id FK
        int seq
        int speaker_user_id FK "nullable"
        string text "음성은 저장 안 함"
        datetime created_at
    }

    minutes {
        int id PK
        int meeting_id FK, UK
        string headline
        string status "summarizing / done / failed"
        datetime created_at
    }

    minutes_item {
        int id PK
        int minutes_id FK
        string kind "decision / discussion / pending"
        int seq
        string text
    }

    task {
        int id PK
        int room_id FK
        int meeting_id FK "nullable"
        string title
        date due_date "nullable"
        int assignee_user_id FK "nullable, 비어 있는 게 정상"
        string state "todo / doing / blocked / done"
        string origin "ai / manual"
        bool confirmed "false가 곧 AI 제안"
        int confirmed_by FK "nullable"
        datetime confirmed_at "nullable"
        bool dropped "필요 없음"
        int done_meeting_id FK "nullable, 회의에서 끝난 일"
        datetime created_at
    }

    notification {
        int id PK
        int room_id FK
        int user_id FK
        string kind "late / blocked / done / meeting_soon / meeting_proposed / meeting_confirmed"
        int task_id FK "nullable"
        int meeting_id FK "nullable"
        string reason
        string dedupe_key "user_id와 함께 유일"
        datetime read_at "nullable"
        datetime created_at
    }

    agent_log {
        int id PK
        int room_id FK
        int user_id FK "nullable"
        string what
        string why
        datetime created_at
    }

    push_subscription {
        int id PK
        int user_id FK
        string endpoint UK
        string p256dh
        string auth
        datetime created_at
    }
```

- 유일: `transcript_segment (meeting_id, seq)`.
- `task`는 `confirmed=false`인 행이 회의록의 "AI 제안"입니다. 확정 전에는 할 일 목록에 넣지 않습니다.
- `notification`은 레인 B가 직접 쓰지 않고 A의 `emit()`을 부릅니다.

## 부모를 지우면

- 기본은 같이 삭제(CASCADE)입니다.
- 아래만 NULL로 비웁니다 (SET NULL).
  - `meeting.scheduling_id` · `meeting.candidate_slot_id`
  - `preference_change.meeting_id`
  - `task.meeting_id` · `task.done_meeting_id` · `task.assignee_user_id` · `task.confirmed_by`
  - `transcript_segment.speaker_user_id`
