# Prompt Policy

> **질문 정책 위임:** 후속 질문의 유형·세션 상한·게이트·확장 질문 허용은
> [`docs/question_strategy.md`](question_strategy.md)가 canonical이다.
> 이 문서는 **기억 초안 추출** 프롬프트 정책만 다룬다.
> (구 정책의 "정확도 확인용 질문 1개"는 `REFLECTION_AGENT_ENABLED=false` 레거시 경로 설명이다.)

## 시스템 역할 정의

프롬프트 파일: `conversation_to_memory/prompts/memory_archive_system_prompt.txt`

GPT에게 부여하는 역할:

> **개인 기억 아카이브 정리자** (상담사·코치 아님)

## 금지 사항 (프롬프트에 명시)

| 금지 | 이유 |
|------|------|
| 긍정적 재해석 | 원문에 없는 의미 부여 |
| 성장 서사 ("견뎌냈다", "성장") | 사용자 미발화 |
| 자기칭찬·교훈·깨달음 | 자기계발 일기화 |
| 미래 감정 강요 | "끝나면 어떤 기분?" |
| 자기계발 후속 질문 | "배운 점은?" |

## 허용 사항

- 원문에 있는 **사건·감정·맥락** 정리
- 원문 근거가 있는 **감정 추출** (`emotion_evidence` 필수)
- 불확실한 해석 → `unsupported_inferences` + `interpretation_risk`
- `memory_candidate` / `model_interpretation` 분리

## JSON 출력 정책

모든 분석 결과는 단일 JSON으로 반환한다. 전체 스키마는 runtime 프롬프트를 따른다.
운영에서 reflection agent가 켜져 있으면 `needs_followup`/`followup_question`은 코드가 비운다.
질문 JSON 스키마는 `question_generation_prompt.txt`와 `question_strategy.md`를 본다.

### 필드 정책 (초안)

- **event_summary**: 사건 중심, 3~5문장, 포장 금지
- **memory_candidate**: 저장 가치 있는 한 덩어리, 성장 서사 금지
- **model_interpretation**: 에이전트 해석 (사실과 분리)
- **needs_followup / followup_question**: 레거시 호환 필드. 운영 경로에서는 질문 단계가 담당

## 후속 질문 (요약)

현행 규칙의 상세·예시는 `question_strategy.md`에 있다.

| 구분 | 값 |
|------|-----|
| 한 번에 보내는 질문 | 1개 |
| 세션 상한 | 최대 2회 |
| 두 번째 질문 | second-question gate 통과 시만 |
| 목적 | 정확도 확인 + 회고 확장 (association 등) |

### 나쁜 질문 (공통 금지 — 초안·질문 모두)

- "이 경험을 통해 무엇을 배웠나요?"
- "힘든 상황을 견뎌낸 자신에게 어떤 말을 해주고 싶나요?"
- "이 일이 끝나면 어떤 기분이 들 것 같나요?"

## 후처리 (코드 레벨)

`conversation_to_memory/memory/fidelity.py`에서 GPT 출력 후:

1. 금지 성장 서사 패턴 탐지
2. `unsupported_inferences` 보강
3. `interpretation_risk` 재평가

프롬프트만으로 100% 방지 불가 → **코드 검증 병행**

## 맥락 전달

분석 시 다음 맥락을 user 메시지에 포함:

- `recent_context` — 최근 기록 (최대 3건)
- `cancelled_draft` — 취소된 초안
- `cancellation_reason` — 취소 당시 사용자 발화
- `followup_already_asked` — 레거시 경로에서 초안 모델에 질문 이미 사용됨을 알림

## Temperature

- 분석/추출: `0.2` (일관성·충실도 우선)
- 질문 생성: `0.45` (유형 다양성)
- 창의적 재해석 방지

## 레거시 프롬프트

- `legacy/interviewer_system_prompt.txt` — **사용 중단** (3~5개 인터뷰 흐름)
- `legacy/memory_extraction_prompt.txt` — **사용 중단** (`memory_archive_system_prompt.txt`로 대체)
