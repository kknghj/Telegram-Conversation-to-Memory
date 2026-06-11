# MVP — Memory Archive Bot

## 정체성

이 봇은 **상담봇·자기계발 일기봇이 아니라 기억 아카이브 봇**입니다.

- 사용자가 말한 내용을 **있는 그대로** 정리·보관
- GPT가 만든 교훈·성장 서사와 사용자의 실제 기억을 **분리**
- **원문 충실도**가 긍정적 재해석보다 우선

## 현재 사용자 흐름

```
기록 시작
  ↓
(취소 초안 있으면) 이어서 / 새로 선택
  ↓
자유 기록 (여러 메시지 가능)
  ↓
「요약」 입력
  ↓
GPT 원문 분석 → 후속 질문 0~1개 (필요 시만)
  ↓
요약 + JSON 검토
  ↓
저장 / 수정 / 취소
  ↓
취소 시 → cancelled_draft 임시 보관 + SQLite drafts 테이블 30일 보관
  ↓
서버 재시작 후에도 「수정」 또는 「기록 시작」으로 복구 가능
```

## 상태 관리

| 키 | 설명 |
|----|------|
| `current_session` | 진행 중 대화·원문 |
| `current_draft` | GPT가 생성한 검토용 초안 |
| `cancelled_draft` | 취소된 초안 (임시 보관) |
| `cancellation_reason` | 취소 당시 사용자 발화 |
| `recent_context` | 최근 원문·요약 맥락 (최대 5건) |
| `persisted_draft_id` | SQLite drafts 테이블 row id |

## SQLite (MVP)

- DB 파일: `data/memory_archive.db`
- `drafts` — active / cancelled / saved 초안
- `memories`, `sessions` — 향후 확장용

### drafts 보관 정책

| status | 정책 |
|--------|------|
| `cancelled` | 30일 보관 후 자동 삭제 |
| `active` | 7일 방치 시 cancelled로 전환 |
| `saved` | 영구 보관 |

### 취소 초안 복구

- 저장 취소 시 SQLite에 `status=cancelled`로 저장
- 「수정」, 「이전 기록 수정」, 「취소한 기록 수정」 → 최근 cancelled draft 불러오기
- 「기록 시작」 시 24시간 내 cancelled draft 있으면 이어쓰기/새로 선택

## JSON 스키마

```json
{
  "topic": "",
  "event_summary": "",
  "user_emotions": [],
  "emotion_evidence": [],
  "people": [],
  "projects": [],
  "tags": [],
  "memory_candidate": "",
  "interpretation_risk": "low | medium | high",
  "unsupported_inferences": [],
  "needs_followup": true,
  "followup_question": ""
}
```

저장 시 `conversation`, `timestamp`, `approved` 필드가 추가됩니다.

## 채널 & 인프라

- Telegram Bot (`python-telegram-bot`)
- OpenAI API (원문 분석 + 구조화)
- Local JSON 저장 (`data/memories/`)

## 코드 구조

- `conversation_to_memory/bot/` — 핸들러, 상태, 세션
- `conversation_to_memory/memory/` — OpenAI 분석, 원문 충실도 검사
- `conversation_to_memory/storage/` — JSON 저장
- `app/database.py` — SQLite 초안·세션 영속화
- `conversation_to_memory/prompts/` — 아카이브 정책 프롬프트

## 이번 MVP에서 하지 않을 것

- Supabase / Vector DB
- Notion 연동
- 자동 저장
- 다중 사용자 인증
- 웹 UI

## 취소 후 명령

| 입력 | 동작 |
|------|------|
| `수정` / `이전 기록 수정` / `취소한 기록 수정` | SQLite에서 취소된 초안 불러와 검토 |
| `새 기록` | 초안 폐기 후 새 시작 안내 |
| `기록 시작` | 24h 내 cancelled draft 있으면 1/2 선택, 없으면 새 세션 |

## 취소 초안 철학

- **취소된 기록은 실패한 기록이 아니라 수정 가능한 초안이다.**
- **저장 취소 시 즉시 삭제하지 않고 SQLite에 보관한다.**
- **기억 아카이브는 최종 저장본뿐 아니라 사용자가 남겼다가 보류한 생각도 관리한다.**

## 관련 문서

- [MEMORY_ARCHIVE_PRINCIPLES.md](./MEMORY_ARCHIVE_PRINCIPLES.md)
- [PROMPT_POLICY.md](./PROMPT_POLICY.md)
