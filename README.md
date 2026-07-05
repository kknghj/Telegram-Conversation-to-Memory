# Conversation-to-Memory MVP

Telegram에서 사용자가 남긴 이야기를 **있는 그대로 정리하고**, 사용자 승인 후 구조화 JSON으로 보관하는 개인 기억 아카이브 봇입니다.

> 상담, 코칭, 긍정적 재해석이 아니라 **원문 기록 → 최소 확인 → 검토 → 승인 → 보관 → 회고** 흐름의 가치를 검증합니다.

## 제품 원칙

- 사용자가 말하지 않은 성장 서사, 교훈, 자기칭찬을 만들지 않습니다.
- 감정은 원문 근거와 함께 기록합니다.
- 불확실한 해석은 `unsupported_inferences`와 `interpretation_risk`로 드러냅니다.
- 후속 질문은 정확한 기록에 꼭 필요할 때만 최대 1개 묻습니다.
- 자동 저장하지 않으며, 사용자가 `저장`을 입력해야 최종 기록이 됩니다.
- 취소된 기록은 삭제하지 않고 일정 기간 수정 가능한 초안으로 보관합니다.

## 사용자 흐름

1. Telegram에서 `기록 시작` 입력
2. 여러 메시지로 사건, 감정, 생각을 자유롭게 기록
3. 기록을 마치면 `요약` 입력
4. OpenAI가 원문 기반 초안 생성
5. 정확도 확인이 필요하면 후속 질문 최대 1개
6. 요약과 구조화 JSON 검토
7. `저장`, `수정`, `취소` 중 선택
8. `저장`한 기억만 최종 저장소에 보관 (`local_json` 기본, `supabase` 선택)
9. 취소한 초안은 SQLite에 보관하고 이후 `수정`으로 복구 가능

## 프로젝트 구조

```text
07-conversation-to-memory/
├── main.py
├── app/
│   └── database.py                  # SQLite 초안 영속화·보관 정책
├── conversation_to_memory/
│   ├── bot/
│   │   ├── handlers.py              # Telegram 사용자 흐름
│   │   ├── session.py               # 사용자별 세션·초안 상태
│   │   └── states.py                # ConversationHandler 상태
│   ├── memory/
│   │   ├── service.py               # OpenAI 원문 분석·구조화
│   │   └── fidelity.py              # 과해석·성장 서사 검사
│   ├── storage/
│   │   ├── base.py                  # MemoryStorage 인터페이스
│   │   ├── local_json.py            # 승인된 기억 JSON 저장 (기본)
│   │   ├── supabase.py              # 승인된 기억 Supabase 저장 (선택)
│   │   └── factory.py               # STORAGE_BACKEND 선택
│   └── prompts/
│       └── memory_archive_system_prompt.txt
├── data/
│   ├── memory_archive.db            # 진행·취소·저장 초안
│   └── memories/                    # 승인된 기억 JSON
├── docs/
└── tests/
```

## 실행

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python main.py
```

`.env`에 다음 값을 설정합니다.

| 변수 | 설명 |
|------|------|
| `TELEGRAM_BOT_TOKEN` | Telegram BotFather에서 발급한 토큰 |
| `OPENAI_API_KEY` | OpenAI API 키 |
| `OPENAI_MODEL` | 선택 사항, 기본값 `gpt-4o-mini` |
| `STORAGE_BACKEND` | 선택 사항, 기본값 `local_json` (`supabase` 가능) |
| `DRAFT_STORAGE_BACKEND` | 선택 사항, 기본값 `sqlite` (`supabase` 가능, Render 운영 권장) |
| `SUPABASE_URL` | `STORAGE_BACKEND=supabase`일 때 필요 |
| `SUPABASE_SECRET_KEY` | `STORAGE_BACKEND=supabase`일 때 필요 (서버 전용) |
| `SUPABASE_MEMORIES_TABLE` | 선택 사항, 기본값 `memories` |
| `SUPABASE_DRAFTS_TABLE` | 선택 사항, 기본값 `drafts` |

Telegram에서 `/start` 또는 `기록 시작`을 보냅니다.

## Transcript Replay

메모장에 모아 둔 `.txt` 기록이나 `.json` 대화 파일을 기존 dev chat 흐름으로 replay할 수 있습니다. 기본값은 dry-run이라 final memory 저장소를 변경하지 않습니다.

```powershell
python -m app.dev_chat --replay data/replay/notes.txt --dry-run
python -m app.dev_chat --replay data/replay/notes.txt --interactive-review
python -m app.dev_chat --replay data/replay/notes.txt --save-final
python -m app.dev_chat --replay data/replay/conversation.json --dry-run
```

자세한 입력 형식과 안전 규칙은 [Transcript Replay Mode](docs/transcript_replay_mode.md)를 참고하세요.

## 테스트

```powershell
pytest -q
```

현재 테스트는 세션 상태, JSON 저장, OpenAI 응답 정규화, 원문 충실도 검사, 취소 초안 복구와 보관 정책을 다룹니다.

## 저장 스키마

```json
{
  "timestamp": "2026-06-11T17:56:09.123456",
  "topic": "부서 내 관계",
  "event_summary": "사용자가 말한 사건 중심 요약",
  "user_emotions": ["답답함"],
  "emotion_evidence": ["원문에서 감정을 뒷받침하는 표현"],
  "people": ["팀장"],
  "projects": [],
  "tags": ["업무", "관계"],
  "memory_candidate": "나중에 다시 읽을 기억 본문",
  "interpretation_risk": "low",
  "unsupported_inferences": [],
  "needs_followup": false,
  "followup_question": "",
  "conversation": [
    {"role": "user", "content": "사용자 원문"}
  ],
  "approved": true
}
```

## 현재 저장 전략

- 승인된 기억 (기본): `data/memories/YYYY-MM-DD_HHMMSS.json` (`STORAGE_BACKEND=local_json`)
- 승인된 기억 (선택): Supabase `memories` 테이블 (`STORAGE_BACKEND=supabase`)
- 진행·취소·저장 초안 상태 (로컬 기본): `data/memory_archive.db` (`DRAFT_STORAGE_BACKEND=sqlite`)
- 진행·취소·저장 초안 상태 (운영 권장): Supabase `drafts` 테이블 (`DRAFT_STORAGE_BACKEND=supabase`)
- `cancelled`: 30일 후 삭제
- 7일 이상 방치된 `active`: `cancelled`로 전환
- `saved`: 삭제하지 않음

### Supabase 최종 기억 저장 (선택)

1. Supabase 프로젝트를 만들고 SQL Editor 또는 CLI로 `supabase/migrations/005_create_memories.sql`과 `supabase/migrations/007_create_drafts.sql`을 실행합니다.
2. `.env`에 `SUPABASE_URL`, `SUPABASE_SECRET_KEY`를 설정합니다.
3. `STORAGE_BACKEND=supabase`로 변경합니다.
4. Render처럼 로컬 디스크가 휘발성인 운영 환경에서는 `DRAFT_STORAGE_BACKEND=supabase`도 설정합니다.

`DRAFT_STORAGE_BACKEND=supabase`일 때 초안/취소/복구 흐름도 Supabase `drafts` 테이블에 보관됩니다. Render 운영에서는 이 설정을 사용해야 30일 임시 보관 정책이 재시작·재배포 후에도 유지됩니다.

## Import Local Memories

기존 `data/memories/*.json`을 Supabase `memories` 테이블로 이전하는 독립 Migration 도구입니다. 원본 JSON 파일은 수정·삭제하지 않으며, 기본 동작은 dry-run(Insert 없음)입니다.

Migration 추적 컬럼을 위해 `supabase/migrations/006_add_migration_tracking_columns.sql`도 함께 실행하세요.

### Dry Run (기본)

```powershell
python scripts/migrate_local_memories_to_supabase.py
python scripts/migrate_local_memories_to_supabase.py --dry-run
```

### Apply

```powershell
python scripts/migrate_local_memories_to_supabase.py --apply
```

결과는 `logs/migration_*.log`와 `reports/migration/latest_migration_report.md`에 기록됩니다.

SQLite의 `memories`, `sessions` 테이블은 향후 확장을 위해 준비되어 있으며, 현재 최종 기억의 기본 저장소는 로컬 JSON입니다.

## Render 배포 (Background Worker)

Telegram Polling Bot을 Render Background Worker에서 24시간 실행할 수 있습니다. `python main.py`만 실행하면 Polling이 시작됩니다.

### 배포 파일

| 파일 | 용도 |
|------|------|
| `render.yaml` | Render Blueprint — Worker 타입, build/start 명령, 기본 env 정의 |
| `runtime.txt` | Python 버전 고정 (`3.12.8`) — Render와 로컬/CI 환경 일치 |

`Procfile`은 Heroku용이라 사용하지 않습니다. Render는 `render.yaml`의 `startCommand`로 시작 명령을 지정합니다.

### GitHub 연동 후 배포

1. 이 저장소를 GitHub에 push합니다.
2. [Render Dashboard](https://dashboard.render.com/) → **New** → **Blueprint** (또는 **Background Worker**).
3. Blueprint를 쓰면 루트의 `render.yaml`을 선택합니다. 수동 생성 시:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python main.py`
4. Environment Variables에 아래 값을 설정합니다 (Dashboard에서 직접 입력, Git에 넣지 않음).

| 변수 | Render 필수 | 설명 |
|------|-------------|------|
| `TELEGRAM_BOT_TOKEN` | 예 | BotFather 토큰 |
| `OPENAI_API_KEY` | 예 | OpenAI API 키 |
| `STORAGE_BACKEND` | 예 | 운영 권장: `supabase` |
| `DRAFT_STORAGE_BACKEND` | 예 | 운영 권장: `supabase` |
| `SUPABASE_URL` | supabase일 때 | Supabase 프로젝트 URL |
| `SUPABASE_SECRET_KEY` | supabase일 때 | 서버 전용 secret key |
| `SUPABASE_MEMORIES_TABLE` | 선택 | 기본 `memories` |
| `SUPABASE_DRAFTS_TABLE` | 선택 | 기본 `drafts` |
| `OPENAI_MODEL` | 선택 | 기본 `gpt-4o-mini` |
| `TELEGRAM_OFFLINE_MODE` | 선택 | 운영에서는 `false` 또는 미설정 |

5. Deploy 후 **Logs** 탭에서 다음 순서로 메시지가 보이면 정상입니다.

```text
Memory Archive Bot 시작
Storage Backend: supabase
Draft Storage Backend: supabase
Supabase 연결 성공 (table=memories)
Supabase drafts 연결 성공 (table=drafts)
Telegram Bot 연결 성공 (@your_bot, id=...)
Telegram Polling 시작
```

6. Telegram에서 `/start` 또는 `기록 시작`으로 동작을 확인하고, `저장` 후 Supabase `memories` 테이블에 row가 생기는지 확인합니다.

### 로그·종료

- 시작 시 Storage Backend, Supabase 연결, Telegram `getMe`, Polling 시작을 INFO로 출력합니다.
- 연결 실패·필수 env 누락 시 명확한 오류 메시지 후 프로세스가 종료됩니다 (Render 로그에서 원인 확인).
- Render가 Worker를 재시작할 때 `SIGTERM`을 보냅니다. `python-telegram-bot`이 이를 처리하고 `Polling 종료` 로그가 남습니다.

### 운영 시 참고

- Worker 디스크는 **휘발성**입니다. Render 운영에서는 `DRAFT_STORAGE_BACKEND=supabase`를 사용해 진행·취소 초안을 Supabase `drafts` 테이블에 보관합니다. 이 설정을 쓰지 않으면 재배포·재시작 시 SQLite 초안 상태가 사라질 수 있습니다.
- 상세 체크리스트: [docs/deployment_checklist.md](docs/deployment_checklist.md)

## MVP 범위 밖

- 상담·코칭·자기계발 조언
- Supabase 저장소 연동은 선택 기능으로 추가되었으며, 다중 사용자 인증과 웹 대시보드는 아직 범위 밖입니다.
- Vector DB와 의미 검색
- 자동 주간 회고
- Notion·Hermes 연동
- 웹 UI, 음성·사진 입력
- 사용자 승인 없는 자동 저장

## 문서

- [제품 비전](docs/vision.md)
- [MVP 범위와 검증 가설](docs/mvp_scope.md)
- [현재 아키텍처](docs/architecture.md)
- [기억 아카이브 원칙](docs/MEMORY_ARCHIVE_PRINCIPLES.md)
- [프롬프트 정책](docs/PROMPT_POLICY.md)
- [향후 로드맵](docs/future_roadmap.md)
- [Render 배포 체크리스트](docs/deployment_checklist.md)
