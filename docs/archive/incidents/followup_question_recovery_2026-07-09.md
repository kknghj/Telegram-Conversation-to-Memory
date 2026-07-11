# Follow-up Question Recovery - 2026-07-09

> 상태: `superseded` — 2026-07-09 후속 질문 회귀와 복구 조치를 남긴 사건 기록입니다. 현행 질문 정책은 `../../question_strategy.md`를 따릅니다. 격리일: 2026-07-11.

## 배경

Supabase `memories`에는 105개 기억이 쌓였지만, 90개 이후 신규/live 기억에서 후속 질문이 나오지 않는 현상이 관찰되었다.

처음에는 `needs_followup` / `followup_question` 컬럼만 기준으로 보면 전체가 0건처럼 보였으나, 실제 질문 여부는 `memories.conversation` 안의 `role = assistant` 메시지를 기준으로 봐야 한다.

## 관측 결과

| 구간 | 기억 수 | assistant 질문 포함 기억 | 질문 포함률 |
| --- | ---: | ---: | ---: |
| 1-90번 초기/과거 기억 | 90 | 80 | 88.9% |
| 91-105번 live 신규 기억 | 15 | 0 | 0.0% |

최신 decision trace 3건은 모두 다음 상태였다.

```json
{
  "evaluated": true,
  "llm_called": true,
  "need_followup": false,
  "generated": false,
  "sent": false,
  "reason": "information_already_complete",
  "strategy": "skip"
}
```

즉 질문 생성기가 실행되지 않은 것이 아니라, 실행 후 질문하지 않기로 판단했다.

## 원인 분석

### 1. Rule 5 이후 나쁜 질문 차단이 강화됨

2026-07-02 전후로 부정 감정 직후 긍정 회상 질문을 막는 Rule 5가 추가되었다.

이 조치는 필요했다. 사용자는 부정 감정 표현 직후 `반대로 즐거웠던 순간`, `극복`, `좋았던 점`처럼 감정을 긍정으로 전환시키는 질문을 싫어한다. 따라서 이 규칙은 유지해야 한다.

문제는 이 안전장치가 이후 전체 질문 생성 판단을 지나치게 보수적으로 만드는 방향으로 작용했다는 점이다.

### 2. 기억 추출 품질 보강이 질문 필요성을 낮춰 보이게 만듦

2026-07-05~2026-07-06 사이에 다음 보강이 들어갔다.

- 가치관 중심 기억 저장
- 미래/현재 시제 검증
- `reflection_seed_candidate` 탐지
- `reflection_value` 보강
- 수정 요청 검증
- 최종 일관성 검사

그 결과 최신 기억은 `interpretation_risk = low`, `unsupported_inferences = []`로 정리되는 경우가 많아졌다.

이 자체는 좋은 변화지만, 질문 생성기는 이를 `더 물을 필요 없음`으로 과하게 해석했다.

### 3. meaning_check 억제 규칙이 전체 질문 억제로 번짐

기존 원칙은 다음과 같았다.

- `interpretation_risk = low`이고 `unsupported_inferences`가 비어 있으면 `meaning_check`를 생성하지 않는다.

이 규칙은 맞다. 정확한 초안에 대해 `이렇게 기록해도 될까요?`를 반복하면 귀찮아진다.

하지만 이 규칙이 association, contrast, value_probe까지 사실상 억제하는 방향으로 작동했다. 사용자가 원하는 것은 의미 확인 질문이 아니라, 원문을 왜곡하지 않는 새 관점 질문이다.

### 4. `information_already_complete`가 너무 많은 상황을 덮음

기존 trace에서는 다음 상황들이 모두 `information_already_complete`로 뭉개질 수 있었다.

- 정말 질문할 손잡이가 없음
- 질문하면 뜬금없어질 위험이 큼
- 요약은 정확하지만 새 생각으로 이어질 손잡이가 있음
- 질문 프롬프트가 안전한 질문을 찾지 못함

이 때문에 최신 3건 중 사용자가 직접 `후속질문이 안 나와 만족도가 떨어진다`고 말한 기억조차 `information_already_complete`로 skip되었다.

## 핵심 결정사항

### 결정 1. 정확함과 질문 가능성을 분리한다

정확하게 요약되었다는 것은 `meaning_check`가 필요 없다는 뜻이지, 모든 후속 질문이 필요 없다는 뜻은 아니다.

새 기준:

```text
accurate_summary != no_question_needed
accurate_summary + reflective_handle = complete_but_expandable
```

### 결정 2. `complete_but_expandable`을 명시적 상태로 다룬다

다음 신호가 있으면 요약이 충분해도 질문을 고려한다.

- 생생한 key_phrase
- 기억이 떠올랐다는 표현
- 아쉬움, 거리낌, 열등감, 불확실성 같은 원문 근거 있는 감정/판단
- 가치 판단, 기준, 원하는 방향, 만들고 싶은 것
- 질문 자체, 새로운 관점, 사용 만족도에 대한 메타 피드백

### 결정 3. meaning_check만 억제하고 association/contrast/value_probe는 살린다

`interpretation_risk = low`이고 `unsupported_inferences = []`이면 meaning_check는 금지한다.

하지만 다음 유형은 여전히 허용한다.

- `association`
- `contrast`
- `value_probe`
- `archive_decision`
- 제한적인 `future_reflection`

### 결정 4. LLM이 `information_already_complete`로 스킵해도 안전한 fallback 질문을 세울 수 있게 한다

LLM이 질문을 생성하지 않았더라도, 코드가 원문 손잡이를 감지하면 grounded fallback 질문을 만든다.

예시:

- `열등감` → 비교 기준이 선명해진 순간을 묻는다.
- `자제해야 하는데` → 아쉬움과 경계 중 기록 중심을 묻는다.
- `후속질문 / 새로운 관점` → 어떤 질문 방식이 새 생각으로 이어졌는지 묻는다.
- key_phrase가 있으면 그 표현을 나중에 읽을 때 같이 떠오를 장면/맥락을 묻는다.

단, 다음 hard stop은 fallback보다 우선한다.

- 피로/중단 신호
- 요약 요청 + 충분한 부정 감정
- positive reframe 위험
- 금지 추론어
- 여러 질문을 한 문장에 넣은 경우

## 적용한 조치

### 코드

`conversation_to_memory/memory/question.py`

- `EXPANSION_SIGNAL_KEYWORDS` 추가
- `has_reflective_expansion_signal()` 추가
- `build_grounded_expansion_question()` 추가
- `validate_question()`에서 LLM skip 결과가 `information_already_complete`이고 원문 손잡이가 있으면 fallback 질문으로 복구
- `_build_question_user_content()`에 `memory_candidate`, `reflection_value`, `memory_type`을 포함해 질문기가 더 풍부한 판단을 할 수 있게 함

### 프롬프트

`conversation_to_memory/prompts/question_generation_prompt.txt`

- `complete_but_expandable` 개념 추가
- `interpretation_risk = low`는 meaning_check 금지 조건이지 전체 질문 금지 조건이 아님을 명시
- skip reason 기준을 세분화

### 테스트

`tests/test_question_generation.py`

- `information_already_complete`라도 `열등감` 같은 원문 손잡이가 있으면 질문을 복구하는 테스트 추가
- `no_reflective_handle`는 계속 skip되는 테스트 추가
- 제품 피드백/후속질문 불만이 expansion signal로 잡히는 테스트 추가

## 기대 효과

- 90개 이후처럼 live 신규 기억에서 질문 생성률이 0%로 떨어지는 현상을 완화한다.
- 질문을 무작정 늘리지 않고, 원문 손잡이가 있는 경우에만 복구한다.
- 사용자가 싫어하는 부정 감정 직후 긍정 전환 질문은 계속 차단한다.
- decision trace에서 질문 실패 원인을 더 세분화해 다음 분석이 쉬워진다.

## 후속 검증

다음 20개 live 신규 기억을 기준으로 확인한다.

| 지표 | 목표 |
| --- | ---: |
| 질문 포함 세션 | 최소 6건 이상 |
| `positive_reframe_risk` 질문 전송 | 0건 |
| 피로/거부 신호 이후 추가 질문 | 0건 |
| 사용자가 별로라고 느낀 질문 | 20% 이하 |
| 질문이 기억을 풍부하게 만든 세션 | 질문 포함 세션의 60% 이상 |

이 지표가 충족되면 `docs/validation_plan.md`의 2단계 회고 씨앗 수집 검증을 본격 진행한다.

## 추가 분석 (2026-07-09 밤) — 수정이 반영되지 않았던 진짜 원인

위 수정 배포 이후에도 신규 기록 2건이 동일하게 `information_already_complete`로 skip되었다.
재분석 결과 원인은 두 가지였다.

### 원인 A. 운영에서 reflection 경로 자체가 꺼져 있었다

- `render.yaml`에 `REFLECTION_AGENT_ENABLED`가 없어 운영 봇은 기본값 false로 동작했다.
- false면 `question_flow.maybe_followup_or_review`가 레거시 분기로 빠져,
  요약 LLM이 준 `draft["needs_followup"]`만 확인하고 `question.py`의
  질문 생성·복구 로직(`validate_question`, `build_grounded_expansion_question`)은 아예 호출되지 않는다.
- 레거시 skip trace의 형태(`llm_called: true, reason: information_already_complete`)가
  reflection 경로의 skip trace와 동일해서 두 경로를 구분할 수 없었고, 이것이 오진의 원인이 됐다.

결정적 증거: skip된 두 메시지 모두 원문에 "모르겠다"가 포함되어 있었다.
reflection 경로였다면 피로 키워드 검사에 걸려 `fatigue_keyword_detected`로 기록됐어야 한다.
`information_already_complete`가 나왔다는 것은 reflection 경로가 실행되지 않았다는 뜻이다.

### 원인 B. 피로 키워드가 긴 성찰형 문장에 오탐

reflection을 켜기만 하면 이번 메시지들은 이번엔 "모르겠다" 때문에
`fatigue_keyword_detected`로 skip됐을 것이다. "왜 그런지 모르겠다" 같은
긴 성찰형 문장의 "모르겠다"는 중단 신호가 아니다.

### 조치

1. `render.yaml`·`.env.example`에 `REFLECTION_AGENT_ENABLED=true`, `REFLECTION_MAX_QUESTIONS=2` 추가 (운영 활성화)
2. `question.py`에 `has_fatigue_signal()` 도입 — 피로 키워드는 25자 이하 짧은 답변에서만 인정,
   긴 본문에서는 "질문 그만" 같은 명시적 중단 표현만 인정
3. question trace에 `engine` 필드(`reflection` / `legacy`) 추가 — 앞으로 어느 경로가 실행됐는지 trace만으로 구분 가능
4. 실제 skip됐던 메시지를 재현하는 회귀 테스트 추가 (`test_long_reflective_feedback_message_recovers_question`)
