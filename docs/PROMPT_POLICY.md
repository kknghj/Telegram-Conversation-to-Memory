# Prompt Policy

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
- 원문 기록 **정확도 확인**용 후속 질문 1개
- 불확실한 해석 → `unsupported_inferences` + `interpretation_risk`

## JSON 출력 정책

모든 분석 결과는 단일 JSON으로 반환:

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

### 필드 정책

- **event_summary**: 사건 중심, 3~5문장, 포장 금지
- **memory_candidate**: 저장 가치 있는 한 덩어리, 성장 서사 금지
- **needs_followup**: 충분히 말했으면 `false`
- **followup_question**: `needs_followup=true`일 때만 1개

## 후속 질문 생성 규칙

### 좋은 질문

- "민원 전화 자체보다 '기다리는 시간'이 더 힘들다고 기록해도 될까요?"
- "용역업체 실수 때문에 억울했다는 점을 핵심으로 남기면 될까요?"
- "이 기록은 감정 기록에 가깝나요, 업무 스트레스 기록에 가깝나요?"

### 나쁜 질문

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
- `followup_already_asked` — 후속 질문 1회 제한

## Temperature

- 분석/추출: `0.2` (일관성·충실도 우선)
- 창의적 재해석 방지

## 레거시 프롬프트

- `interviewer_system_prompt.txt` — **사용 중단** (3~5개 인터뷰 흐름)
- `memory_extraction_prompt.txt` — **사용 중단** (`memory_archive_system_prompt.txt`로 대체)
