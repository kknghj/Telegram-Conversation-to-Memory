# Question Strategy

회고형 대화 에이전트가 생성하는 후속 질문의 **유형·목적·사용 조건**을 정의한다.  
질문 생성 로직(`conversation_to_memory/memory/question.py`, `question_quality.py`)과 프롬프트(`question_generation_prompt.txt`)의 단일 기준 문서다.

사고 경위는 `docs/archive/incidents/`에 남기고, 이 문서는 **현행 규칙만** 유지한다.

---

## 1. 설계 원칙

1. **원문 충실** — 질문은 기록을 왜곡하지 않고 확장한다.
2. **`accurate_summary != no_question_needed`** — 기억 정확도와 회고 확장 가능성을 독립 판단한다.
3. **유형 다양화** — `meaning_check`만 반복하지 않는다.
4. **후보 생성과 검증 분리** — LLM이 곧바로 skip하지 말고 후보를 만든 뒤 검증한다.
5. **사용자 프로필 정렬** — `user_conversation_profile.md`의 연상형·감각 중심 성향을 따른다.
6. **추적 가능** — 각 질문에 `question_mode`와 decision trace를 남긴다.

---

## 2. archive_gap / reflective_handle

| 개념 | 의미 |
|------|------|
| `archive_gap` | 현재 기록을 정확히 저장하기 위해 부족한 정보 (`none` / `minor` / `major`) |
| `reflective_handle_strength` | 정확한 기록 너머로 새 생각을 만들 원문 손잡이 (`none` / `weak` / `strong`) |

### 결정 규칙

```text
hard_stop이 있으면 질문하지 않음

archive_gap=major
→ meaning_check 후보 생성 가능

archive_gap=none 또는 minor
AND reflective_handle_strength=strong
→ association, contrast, value_probe, archive_decision,
   memory_link, 제한적인 future_reflection 후보 생성 가능

archive_gap=none이라고 전체 질문을 생략하지 않음
```

`interpretation_risk=low`, `unsupported_inferences=[]`는 **meaning_check 금지 조건**으로만 사용한다. 전체 질문 금지 조건으로 쓰지 않는다.

`information_already_complete` 하나로 skip을 뭉개지 않는다. 최소 구분 사유:

```text
no_reflective_handle
answered_already
redundant_question
low_salience_anchor
category_mismatch
off_topic
low_expected_gain
fatigue_keyword_detected
question_rejected
positive_reframe_risk
max_questions_reached
```

---

## 3. 질문 유형 분류

### 3.1 meaning_check — 의미·기록 확인

| 항목 | 내용 |
|------|------|
| **목적** | 요약·강조 포인트가 사용자 의도와 일치하는지 확인 |
| **사용 조건** | `archive_gap=major` 또는 `interpretation_risk` ≥ medium |
| **피해야 할 상황** | 직전 질문도 meaning_check; 사용자가 이미 명확히 말함; 세션에서 이미 1회 사용 |

**제한 규칙**

- 세션당 **최대 1회**
- `interpretation_risk: low`이고 `unsupported_inferences`가 비어 있으면 **생성하지 않음**

### 3.2 association — 연상 확장

| 항목 | 내용 |
|------|------|
| **목적** | 독서모임식 꼬리 질문으로 사고를 옆으로 확장 |
| **사용 조건** | reflective handle이 있고 핵심 앵커 salience ≥ medium |
| **피해야 할 상황** | 이미 답한 내용; 낮은 중요도 주변 예시 확대 |

### 3.3 contrast / value_probe

비교·가치 탐색은 **같은 추상화 수준**과 **공통 비교축**이 있을 때만 허용한다.

- 거절: 콩국수 vs 감정 기반 추천
- 허용: 음식명 기반 추천 vs 감정 기반 추천, 완성 우선 vs 상금 우선

### 3.4 memory_link / future_reflection / archive_decision / emotion_probe

기존 목적을 유지한다. `archive_decision`은 여러 테마 중 기록 중심 선택에 쓴다.

---

## 4. 질문 후보 생성과 검증

```text
1. 원문에서 질문 가능한 앵커와 미탐색 각도를 찾음
2. 질문 후보 1~3개 생성
3. 후보별 품질 검증
4. 가장 좋은 후보만 전송
5. 전부 탈락하면 질문 없이 REVIEW
```

후보 필드:

```json
{
  "grounding_quote": "",
  "anchor": "",
  "anchor_salience": "low | medium | high",
  "unexplored_dimension": "",
  "question_mode": "",
  "candidate_question": "",
  "expected_reflective_gain": "low | medium | high",
  "already_answered": false,
  "same_abstraction_level": true,
  "comparison_axis": ""
}
```

검증 조건:

```text
already_answered=false
anchor_salience=medium 이상
expected_reflective_gain=medium 이상
비교 질문이면 same_abstraction_level=true 및 comparison_axis 존재
```

---

## 5. 질문 수와 두 번째 질문 게이트

`REFLECTION_MAX_QUESTIONS=2`를 유지한다. 2회는 목표가 아니라 상한이다.

두 번째 질문 허용 조건:

```text
첫 응답 유형이 followup_answer
첫 답변에서 새로운 정보가 실제로 추가됨
새로운 unresolved point 또는 strong reflective handle이 생김
첫 질문의 단순 반복이 아님
사용자 피로·중단·거부·정정 신호가 없음
```

차단: 원문 반복 답변, 패스, 질문 거부, 메타 피드백, 수정 요청, 피로 신호.

---

## 6. 후속 응답 분류

FOLLOWUP 입력을 기억 원문에 넣기 전에 분류한다.

```text
followup_answer
pass
fatigue_or_stop
question_rejection
meta_feedback
correction
```

- `followup_answer`만 기억 원문에 포함
- `pass` / `fatigue_or_stop` / `question_rejection` / `meta_feedback`는 원문 제외 후 REVIEW
- `question_rejection` / `meta_feedback`는 실패 기록
- `correction`은 수정 흐름으로 전달

세션은 `original_user_texts`, `accepted_followup_answers`, `interaction_feedback`를 구분한다.

---

## 7. 엔티티 역할

```json
{
  "people": [],
  "projects": [],
  "tools": [],
  "organizations": [],
  "events": []
}
```

- `people`: 사람만. GPT/ChatGPT/Cursor 등 비인간은 제외
- `projects`: 지속적으로 개발·관리되는 결과물 이름
- `tools`: GPT, Cursor, Codex, Notion 등
- `events`: 공모전·행사·프로그램
- 공모전 이름을 특정 앱에 전역 매핑하지 않는다

---

## 8. Safety Rules (현행 요약)

기존 failure taxonomy Rule 1~7은 유지한다.

| Rule | 의미 |
|------|------|
| 1 | 기억 불가 신호 후 질문 종료 |
| 2 | 한국어 조건문을 사람 관계로 오해석 금지 |
| 3 | 사용자 수정 우선 |
| 4 | 자기 검증 / 중복·저중요도·카테고리불일치·메타피드백 umbrella |
| 5 | 부정 감정 직후 긍정 회상 질문 금지 |
| 6 | 가치관이 사건 나열에 가려지지 않게 |
| 7 | 부분 수정 반영(`correction_partial`)은 실패 |

런타임 archive 프롬프트의 EditChecklist / ConsistencyCheck는 위 Rule 번호와 다른 네임스페이스다.

추가 강조:

- 이미 답한 내용 → `answered_already`
- 낮은 중요도 앵커 → `low_salience_anchor`
- 추상화 수준 불일치 비교 → `category_mismatch`
- 질문 피드백 → 기억 원문 제외

**후속 질문은 최대 2회**이며, 2회째는 게이트 통과 시에만 허용한다.

부정 감정 직후 긍정 회상 질문(Rule 5)은 계속 금지한다.

---

## 9. Decision Trace / 관측 지표

```json
{
  "engine": "reflection",
  "question_round": 1,
  "archive_gap": "none",
  "reflective_handle_strength": "strong",
  "candidate_count": 3,
  "selected_anchor": "",
  "selected_question_mode": "",
  "rejected_candidates": [{"question": "", "reason": "answered_already"}],
  "second_question_allowed": false,
  "second_question_gate_reason": "",
  "sent": false,
  "final_reason": ""
}
```

관측 지표(질문 강제 생성 금지):

```text
question_candidate_not_generated
question_candidate_generated
question_candidate_rejected
question_sent
second_question_gate_passed
second_question_gate_rejected
```

---

## 10. 테스트 관점

| 케이스 | 기대 |
|--------|------|
| 원문에 이미 연결 설명 | 같은 연결 재질문 차단 |
| archive_gap=none + strong handle | 확장 질문 가능 |
| 콩국수 vs 감정 기반 추천 | category_mismatch |
| 메타 피드백 | 원문 제외 + failure 기록 |
| 패스/거부 | 두 번째 질문 없음 |
| GPT | people 제외, tools 포함 |
| 여름 메뉴 추천앱 + 토스 공모전 | project / event 분리 |

구현: `tests/test_question_quality_regression.py`, `tests/test_question_quality_replay.py`.  
관련 incident: `docs/archive/incidents/question_quality_and_feedback_contamination_2026-07-12.md`.
