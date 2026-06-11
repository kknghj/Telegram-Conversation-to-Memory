# Architecture - Current MVP

## 시스템 구조

```text
┌─────────────┐     ┌────────────────┐     ┌──────────────────┐
│  Telegram   │────▶│   Bot Layer    │────▶│  Memory Service  │
│  (Mobile)   │◀────│ handlers/state │◀────│ OpenAI + Fidelity│
└─────────────┘     └───────┬────────┘     └────────┬─────────┘
                            │                       │
                    ┌───────▼────────┐      ┌───────▼────────┐
                    │ SQLite Drafts  │      │ Archive Prompt │
                    │ active/cancel  │      │ policy (.txt)  │
                    └────────────────┘      └────────────────┘
                            │
                    ┌───────▼────────┐
                    │ Local JSON     │
                    │ approved only  │
                    └────────────────┘
```

| 레이어 | 책임 |
|--------|------|
| Telegram | 사용자 입력, 검토 결과, 명령 응답 |
| Bot Layer | 대화 상태, 세션 데이터, 저장·수정·취소 라우팅 |
| Memory Service | 원문을 구조화 JSON으로 분석 |
| Fidelity | 원문에 없는 성장 서사·과해석 탐지 |
| SQLite | 진행·취소·저장 초안 상태와 복구 정보 보관 |
| Local JSON | 사용자가 승인한 최종 기억 보관 |

## 데이터 흐름

```text
1. [IDLE]
   사용자 -> "기록 시작"
   최근 취소 초안이 있으면 이어서/새로 선택

2. [RECORDING]
   사용자 -> 여러 메시지로 자유 기록
   Bot -> user_data와 SQLite active draft 갱신
   사용자 -> "요약"

3. [ANALYZE]
   Memory Service -> 원문 기반 draft JSON 생성
   Fidelity -> unsupported_inferences와 interpretation_risk 검증

4. [FOLLOWUP, 선택]
   정확한 기록에 정보가 꼭 필요할 때 질문 1개
   답변 후 다시 분석하며 추가 질문은 금지

5. [REVIEW]
   Bot -> 사건 요약 + 구조화 JSON
   사용자 -> "저장" | "수정 ..." | "취소"

6-A. [SAVE]
   LocalJsonStorage -> 승인된 기억 JSON 저장
   SQLite draft -> saved 상태

6-B. [EDIT]
   수정 요청을 포함해 원문 재분석
   다시 REVIEW

6-C. [CANCEL]
   메모리와 SQLite에 cancelled draft 보관
   이후 "수정" 또는 "기록 시작"으로 복구 가능
```

## Conversation 상태

`python-telegram-bot`의 `ConversationHandler`와 `context.user_data`를 사용합니다.

| 상태 | 역할 |
|------|------|
| `RESUME_CHOICE` | 취소 초안을 이어갈지 새로 시작할지 선택 |
| `RECORDING` | 여러 메시지로 원문 수집 |
| `FOLLOWUP` | 선택적 확인 질문 1회 처리 |
| `REVIEW` | 저장·수정·취소 선택 |
| `EDIT` | 별도 메시지로 수정 지시 수집 |

## 사용자별 세션 데이터

| 키 | 내용 |
|----|------|
| `current_session` | `user_texts`, `conversation` |
| `current_draft` | 검토 중인 구조화 초안 |
| `cancelled_draft` | 최근 취소 초안 |
| `cancellation_reason` | 취소 당시 맥락 |
| `recent_context` | 최근 기록 맥락, 최대 5건 |
| `followup_asked` | 후속 질문 1회 제한 |
| `persisted_draft_id` | SQLite 초안 식별자 |

Telegram의 사용자 ID를 SQLite `user_id`로 사용하며, `context.user_data`도 사용자별로 격리됩니다. 현재 제품 검증은 개인 사용을 중심으로 하며 별도 인증 시스템은 없습니다.

## 모듈 책임

```text
main.py
├── 앱 초기화, 환경변수 검사, 상태 라우팅
app/database.py
├── drafts/memories/sessions 테이블
└── 초안 저장·복구·보관 정책
conversation_to_memory/
├── bot/
│   ├── handlers.py
│   ├── session.py
│   └── states.py
├── memory/
│   ├── service.py
│   └── fidelity.py
├── storage/
│   └── local_json.py
└── prompts/
    └── memory_archive_system_prompt.txt
```

`interviewer_system_prompt.txt`와 `memory_extraction_prompt.txt`는 초기 다문항 인터뷰 방식의 레거시 파일이며 현재 흐름에서는 사용하지 않습니다.

## OpenAI 호출

| 항목 | 현재 정책 |
|------|-----------|
| 역할 | 개인 기억 아카이브 정리자 |
| 입력 | 사용자 원문, 대화, 최근 맥락, 취소 맥락, 수정 요청 |
| 출력 | 단일 구조화 JSON |
| 모델 | `OPENAI_MODEL`, 기본 `gpt-4o-mini` |
| temperature | `0.2` |
| 후속 질문 | 정확도 확인 목적, 최대 1개 |

OpenAI 응답은 `normalize_draft()`로 필드를 정규화한 뒤 `validate_draft()`에서 과해석 위험을 검사합니다.

## 저장 구조

### 승인 기억

`LocalJsonStorage.save(memory) -> str` 계약으로 `data/memories/`에 저장합니다. 향후 Supabase 구현도 같은 저장 인터페이스를 따릅니다.

### SQLite 초안

| 테이블 | 현재 용도 |
|--------|-----------|
| `drafts` | 실제 사용: active, cancelled, saved 초안 |
| `memories` | 향후 DB 기반 최종 기억 저장용 |
| `sessions` | 향후 세션 상태 확장용 |

보관 정책:

- `cancelled`: 30일 후 삭제
- 7일 이상 방치된 `active`: `cancelled`로 전환
- `saved`: 삭제하지 않음

## 보안과 운영

- `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`는 `.env`에서 로드합니다.
- `.env`, 가상환경, 저장된 기억은 Git 제외 대상으로 설정합니다.
- 앱 시작 시 SQLite 테이블 생성과 초안 정리를 수행합니다.
- 승인 전 초안과 승인된 최종 기억은 서로 다른 저장 책임을 가집니다.
