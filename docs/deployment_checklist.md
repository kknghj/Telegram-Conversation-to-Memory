# Render 배포 체크리스트

Telegram Conversation to Memory Bot을 Render Background Worker로 운영할 때 따라갈 단계입니다.

## 사전 준비

- [ ] GitHub 저장소에 최신 코드 push
- [ ] Telegram BotFather에서 Bot Token 발급
- [ ] OpenAI API Key 준비
- [ ] Supabase 프로젝트 생성
- [ ] `supabase/migrations/005_create_memories.sql` 실행
- [ ] (Migration 사용 시) `supabase/migrations/006_add_migration_tracking_columns.sql` 실행

## Render Worker 생성

- [ ] [Render Dashboard](https://dashboard.render.com/) 로그인
- [ ] **New** → **Blueprint** → 저장소 연결 → `render.yaml` 적용  
  또는 **New** → **Background Worker** → 같은 저장소 연결
- [ ] Service name: `conversation-to-memory-bot` (Blueprint 기본값)
- [ ] **Build Command:** `pip install -r requirements.txt`
- [ ] **Start Command:** `python main.py`
- [ ] Plan: Starter 이상 (Worker는 유료 플랜 필요)

## GitHub 연결

- [ ] Render에서 GitHub 계정 연동
- [ ] 이 저장소 선택
- [ ] Branch: `main` (또는 배포 브랜치)
- [ ] Auto-Deploy: push 시 자동 배포 (권장)

## Environment Variables

Render Dashboard → Service → **Environment** 에서 설정:

| 변수 | 값 | 비고 |
|------|-----|------|
| `TELEGRAM_BOT_TOKEN` | BotFather 토큰 | Secret |
| `OPENAI_API_KEY` | OpenAI 키 | Secret |
| `STORAGE_BACKEND` | `supabase` | 운영 권장 |
| `SUPABASE_URL` | `https://xxx.supabase.co` | Secret |
| `SUPABASE_SECRET_KEY` | service role / secret key | Secret, 프론트에 노출 금지 |
| `SUPABASE_MEMORIES_TABLE` | `memories` | 선택 |
| `OPENAI_MODEL` | `gpt-4o-mini` | 선택 |
| `TELEGRAM_OFFLINE_MODE` | `false` | 운영에서 dev 모드 금지 |

로컬 개발용 변수(`DEV_CHAT_USER_ID`, `REFLECTION_*` 등)는 Render에 넣지 않아도 됩니다.

## 첫 배포

- [ ] **Manual Deploy** 또는 push로 배포 트리거
- [ ] Build 로그: `pip install -r requirements.txt` 성공
- [ ] Deploy 상태: **Live**

## 로그 확인

Logs 탭에서 아래 순서 확인:

```text
Memory Archive Bot 시작
Storage Backend: supabase
OpenAI Model: gpt-4o-mini
Supabase 연결 성공 (table=memories)
Draft cleanup: ...
Telegram Bot 연결 성공 (@..., id=...)
Telegram Polling 시작 (stop_signals=['SIGINT', 'SIGTERM'])
```

실패 시 흔한 메시지:

| 로그 | 조치 |
|------|------|
| `필수 환경변수 누락: TELEGRAM_BOT_TOKEN` | Token env 추가 |
| `필수 환경변수 누락: OPENAI_API_KEY` | OpenAI key 추가 |
| `STORAGE_BACKEND=supabase이지만 ... SUPABASE_URL` | Supabase env 추가 |
| `Supabase 연결 실패` | URL/key, migration, 테이블명 확인 |
| `Telegram Bot 연결 실패` | Token 오타, Bot 비활성화 여부 확인 |

## Telegram 테스트

- [ ] Bot과 1:1 채팅에서 `/start` 또는 `기록 시작`
- [ ] 짧은 기록 → `요약` → 검토 → `저장`
- [ ] Bot이 저장 완료 응답을 반환하는지 확인

## Supabase 저장 확인

- [ ] Supabase Dashboard → Table Editor → `memories`
- [ ] 방금 저장한 기록 row 존재 (`source=telegram`, `approved=true`)
- [ ] `raw_memory` JSON 필드 내용 확인

## 재배포·종료

- [ ] 코드 push 시 Auto-Deploy로 재시작되는지 확인
- [ ] 재시작 로그에 `Polling 종료 — Bot을 안전하게 중지합니다.` 가 보이면 graceful shutdown 정상
- [ ] Worker 재시작 후 Telegram Polling이 다시 붙는지 확인

## 알려진 운영 제약

- Worker 로컬 디스크는 휘발성입니다. SQLite 초안(`data/memory_archive.db`)은 재시작 시 유실될 수 있습니다.
- 승인된 최종 기억은 `STORAGE_BACKEND=supabase`일 때 Supabase에 영구 보관됩니다.
- 동일 Bot Token으로 로컬과 Render를 동시에 polling하면 충돌합니다. 운영 배포 후 로컬 `python main.py`는 중지하세요.
