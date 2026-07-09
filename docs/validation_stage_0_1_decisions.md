# 0-1단계 검증 결정사항

작성일: 2026-07-09  
대상 저장소: `kknghj/Telegram-Conversation-to-Memory`  
대상 Supabase 프로젝트: `Telegram conversation to memory` (`beexxgsjutmwptitabsu`)

## 요약 판단

Supabase 접속은 정상이며, 현재 public schema에는 6개 테이블이 확인된다.

| 테이블 | 행 수 | 용도 판단 |
|---|---:|---|
| `memories` | 105 | 승인 기억 저장소 |
| `drafts` | 14 | 초안/취소/저장 상태 |
| `mvp_evaluations` | 2 | MVP 라운드 평가 |
| `reflection_evaluations` | 14 | 패턴 카드 평가 |
| `interpretation_failures` | 4 | 질문/해석 실패 로그 |
| `decision_traces` | 3 | 생성/질문 판단 추적 |

0단계 평가 기반 정리는 진행 가능하며, 기존 평가 체계는 장기 콘텐츠 평가 체계로 확장할 수 있다.

1단계 기억 기질 품질 검증도 진행 가능하다. 현재 105개 기억은 Reporter 후보 발견 POC로 넘어갈 최소 조건을 대체로 충족한다. 다만 `reflection_seed_candidate`와 일부 장기 분석 필드는 아직 안정화되지 않았으므로, 다음 단계 진입은 "조건부 통과"로 본다.

---

## 참고한 방향 문서

- `docs/validation_plan.md`
- `docs/vision.md`
- `docs/future_roadmap.md`
- `docs/reflection_evaluation.md`
- `docs/evaluation_supabase_integration.md`
- `data/evaluation/mvp_round2_2026-06-19.json`
- `data/evaluation/mvp_round3_2026-07-04.json`
- `data/evaluation/reflection_evaluations.jsonl`
- Supabase public schema 및 `memories` 집계

이 문서들의 공통 방향은 다음으로 정리된다.

1. 제품의 북극성은 생산성/코칭이 아니라 "사용자의 삶을 더 흥미롭게 읽어주는 개인 AI"다.
2. 기억은 최종 산출물이 아니라 장기 콘텐츠 생성을 위한 신뢰 가능한 기질이다.
3. 좋은 콘텐츠는 `맞는가`와 `읽고 싶은가`를 동시에 통과해야 한다.
4. 원문 근거, 승인 기억, 해석 위험도, 반례 검토가 없는 후보는 발행하지 않는다.
5. 콘텐츠는 생성 즉시 노출하지 않고 Reporter, Editor, Editor-in-Chief 흐름에서 숙성한다.

---

## 0단계. 평가 기반 정리

### 결정 0-1. 기존 평가 필드는 유지한다

다음 필드는 기존 36건, 50건, 88건 평가와 이후 콘텐츠 평가를 이어 붙이는 핵심 축으로 유지한다.

| 필드 | 유지 이유 |
|---|---|
| `accuracy` | 사용자 관점에서 맞는 해석인지 판단 |
| `evidence` | 원문/승인 기억 근거 충분성 판단 |
| `interesting` | 단순 정확도를 넘어 읽을 만한 관점인지 판단 |
| `revisit` | 다시 열어보고 싶은지 판단 |
| `action` | keep/revise/discard/postpone 운영 판단 |
| `failure_type` | 실패를 다음 규칙과 프롬프트에 반영 |
| `user_comment` | 사용자 검증의 원문 맥락 보존 |

### 결정 0-2. 콘텐츠 발행 단계용 평가 필드를 추가한다

장기 비전이 "흥미롭고 다시 읽고 싶은 콘텐츠"이므로, 기존 평가 필드에 다음을 추가한다.

| 필드 | 값 | 사용 단계 |
|---|---|---|
| `fun` | boolean | Style Editor, Draft |
| `taste_fit` | `high`, `medium`, `low`, `unknown` | Style Editor, Feedback Steward |
| `too_much` | boolean | Style Editor, Editor-in-Chief |
| `item_type` | `candidate`, `hook`, `draft`, `published_content`, `memory_substrate` | 전 단계 |
| `period_start`, `period_end` | date | 라운드 비교 |
| `source_memory_ids` | array | Reporter 이후 필수 |
| `interpretation_risk` | `low`, `medium`, `high`, `unknown` | Editor 이후 필수 |
| `counter_evidence_checked` | boolean | Editor 이후 필수 |

`fun`은 근거 기준을 낮추는 면허가 아니다. `fun=true`이면서 `evidence=weak|wrong`이면 기본 실패 유형은 `FUN_BUT_UNGROUNDED`로 둔다.

### 결정 0-3. 실패 유형은 기존 taxonomy에 콘텐츠 실패를 붙인다

기존 실패 유형은 유지한다.

- `SEARCH_FAILURE`
- `CONNECTION_FAILURE`
- `INTERPRETATION_FAILURE`
- `OBVIOUS_INSIGHT`
- `OVER_GENERALIZATION`
- `DATA_INSUFFICIENT`
- `DUPLICATED_CARD`

콘텐츠 단계에는 다음을 추가한다.

- `HOOK_TOO_FLAT`
- `HOOK_TOO_MUCH`
- `TASTE_MISMATCH`
- `BORING_BUT_TRUE`
- `FUN_BUT_UNGROUNDED`
- `PUBLISHING_FATIGUE`

현재 `reflection_evaluations.failure_type`의 DB CHECK constraint는 이 확장 taxonomy를 모두 허용하지 않는다. 따라서 당장은 기존 테이블에 무리하게 덧붙이기보다 새 평가 테이블을 설계하는 편이 안전하다.

### 결정 0-4. 장기 콘텐츠 평가는 별도 테이블이 적합하다

현재 `reflection_evaluations`는 패턴 카드 평가에 맞춰져 있고, CHECK constraint도 기존 회고 카드 실패 유형에 묶여 있다. 장기적으로는 다음 중 하나가 필요하다.

권장안: `content_evaluations` 신규 테이블

이유:

- `candidate`, `hook`, `draft`, `published_content`를 같은 체계로 평가해야 한다.
- `fun`, `taste_fit`, `too_much`, `source_memory_ids`, `counter_evidence_checked`가 필요하다.
- 기존 `reflection_evaluations`의 enum/constraint를 억지로 늘리면 과거 회고 평가와 미래 콘텐츠 평가가 섞인다.
- `reflection_evaluations`는 기존 MVP 비교 기준으로 보존하는 것이 좋다.

단기 운영안:

- 0-1단계 문서화와 수동 검증은 Markdown/JSONL로 먼저 진행한다.
- Reporter 후보 POC 이후 `content_evaluations` 테이블을 추가한다.
- 기존 Supabase mirror 원칙은 유지한다: 로컬 JSONL/JSON이 canonical, Supabase는 best-effort mirror.

### 0단계 통과 판단

판정: 통과

근거:

- 36건, 50건, 88건 평가가 같은 축으로 연결된다.
- 50건 평가에서는 `conditional_success`, 88건 평가에서는 `partial_success` 및 패턴 카드 사용자 검증 5건이 남아 있다.
- 88건 평가에서 accepted 3건, partial 1건, rejected 1건이 확인되어 `accuracy`, `evidence`, `interesting`, `revisit`, `action` 축이 실제로 작동했다.
- 질문 품질은 별도 축으로 유지해야 한다는 교훈이 확인되어 있다.

---

## 1단계. 기억 기질 품질 검증

### Supabase 집계

기준 시점의 `memories` 테이블은 105건이며 모두 `approved=true`다.

| 항목 | 결과 | 비율 | 판단 |
|---|---:|---:|---|
| 승인 기억 | 105/105 | 100.0% | 통과 |
| primary evidence 존재 | 105/105 | 100.0% | 통과 |
| `schema_version=2` | 101/105 | 96.2% | 통과, 단 여유 작음 |
| `event_summary` 채움 | 101/105 | 96.2% | 통과 |
| `memory_candidate` 채움 | 105/105 | 100.0% | 통과 |
| `interpretation_risk` 채움 | 101/105 | 96.2% | 통과 |
| `key_phrases` 비어 있지 않음 | 86/105 | 81.9% | 통과 |
| `emerging_themes` 비어 있지 않음 | 72/105 | 68.6% | 통과 |
| `key_phrases` 또는 `emerging_themes` 중 하나 이상 | 86/105 | 81.9% | 통과 |
| `open_questions` 비어 있지 않음 | 17/105 | 16.2% | 관찰 지표 |
| `reflection_seed_candidate=true` | 2/105 | 1.9% | 미통과 |
| `reflection_value=high` | 5/105 | 4.8% | 낮음 |
| `reflection_value=medium|high` | 83/105 | 79.0% | 활용 가능 |
| `unsupported_inferences` 존재 | 6/105 | 5.7% | 검토 필요 |

### 해석 위험도 분포

| `interpretation_risk` | 건수 | 판단 |
|---|---:|---|
| `low` | 92 | 기본 후보군 |
| `medium` | 8 | Editor 검토 후 후보화 |
| `high` | 1 | 자동 후보 진입 금지 |
| null | 4 | legacy로 분리 |

### 스키마 상태

| `schema_version` | 건수 | 판단 |
|---|---:|---|
| 1 | 4 | legacy schema |
| 2 | 101 | current schema |

`schema_version=2` 비율은 96.2%로 기준 95%를 넘는다. 다만 105건 중 4건만 더 문제가 생겨도 95% 아래로 떨어질 수 있으므로 다음 라운드 전 legacy 4건은 별도 표시하거나 보강하는 것이 좋다.

### 기억 유형 분포

| `memory_type` | 건수 | 판단 |
|---|---:|---|
| `event` | 87 | 기본 사건 기억 |
| `reflection_seed` | 13 | 잠재 회고 재료 |
| `observation` | 5 | 관찰형 기억 |

여기서 주의할 점은 `memory_type=reflection_seed`가 13건인 반면, `reflection_seed_candidate=true`는 2건뿐이라는 점이다. 현재 시스템에서는 `reflection_seed_candidate`가 장기 콘텐츠 후보 품질 지표로 안정적이지 않다.

### 1단계 기준별 판정

| 기준 | 목표 | 현재 | 판정 |
|---|---:|---:|---|
| primary evidence rate | 95% 이상 | 100.0% | 통과 |
| 최신 schema 비율 | 95% 이상 | 96.2% | 통과 |
| `event_summary`/`memory_candidate` 결손 | 5% 이하 | 3.8% / 0.0% | 통과 |
| `key_phrases` 또는 `emerging_themes` 채움 | 60% 이상 | 81.9% | 통과 |
| seed 후보 중 장기 재료 납득률 | 70% 이상 | 사용자 검토 전 | 보류 |
| high-risk 자동 후보 진입 방지 | 0건이어야 함 | 운영 규칙 필요 | 조건부 |

### 1단계 최종 판단

판정: 조건부 통과

다음 단계인 Reporter 후보 발견 POC는 시작해도 된다. 다만 `reflection_seed_candidate`는 현재 품질 검증의 주 지표로 쓰기 어렵다. 당분간 Reporter 후보는 다음 조건으로 뽑는다.

1. `approved=true`
2. primary evidence 존재
3. `schema_version=2`
4. `interpretation_risk='low'`
5. `key_phrases` 또는 `emerging_themes`가 비어 있지 않음
6. `reflection_value in ('medium', 'high')`

`interpretation_risk='medium'`은 자동 후보가 아니라 Editor 검토 대기열로 보낸다. `interpretation_risk='high'`와 legacy schema 4건은 Reporter 자동 후보에서 제외한다.

---

## 앞으로의 평가 변수

### memory_substrate 평가 변수

1단계 이후에도 기억 기질은 별도 평가 축으로 남긴다.

| 변수 | 의미 |
|---|---|
| `primary_evidence_present` | conversation 안에 사용자 원문이 있는가 |
| `schema_current` | 현재 스키마인가 |
| `event_summary_quality` | 사건 요약이 비어 있거나 무의미하지 않은가 |
| `memory_candidate_quality` | 나중에 다시 읽을 기억 본문으로 쓸 수 있는가 |
| `key_phrase_density` | 사용자의 표현이 남아 있는가 |
| `theme_density` | 연결 후보로 쓸 주제가 남아 있는가 |
| `reflection_value` | 회고/콘텐츠 재료 가능성 |
| `interpretation_risk` | 자동 후보 진입 가능 여부 |
| `unsupported_inference_count` | 근거 없는 추론 위험 |
| `legacy_schema` | 후보 생성 전 보강 필요 여부 |

### content_candidate 평가 변수

Reporter 이후에는 다음을 사용한다.

| 변수 | 의미 |
|---|---|
| `source_memory_ids` | 근거 기억 ID |
| `source_memory_count` | 패턴 단정 가능성 |
| `connection_type` | 반복 표현, 가치관, 프로젝트 흐름, 관계, 장면, 열린 질문 등 |
| `accuracy` | 사용자 기준으로 맞는가 |
| `evidence` | 근거가 충분한가 |
| `interesting` | 흥미로운가 |
| `revisit` | 다시 읽고 싶은가 |
| `fun` | 문장 맛이나 위트가 있는가 |
| `taste_fit` | 사용자 취향과 맞는가 |
| `too_much` | 단정, 과장, 놀림이 선을 넘었는가 |
| `counter_evidence_checked` | 반례를 확인했는가 |
| `action` | keep/revise/discard/postpone |
| `failure_type` | 실패 유형 |

---

## 기억 검증 기준

### Reporter 자동 후보 진입 기준

자동 후보에 들어갈 수 있는 기억:

- `approved=true`
- primary evidence가 있다.
- `schema_version=2`
- `interpretation_risk='low'`
- `event_summary`와 `memory_candidate`가 모두 채워져 있다.
- `key_phrases` 또는 `emerging_themes` 중 하나 이상이 비어 있지 않다.
- `reflection_value='medium'` 또는 `reflection_value='high'`

자동 후보에서 제외할 기억:

- `interpretation_risk='high'`
- `schema_version=1`
- primary evidence 없음
- event summary 또는 memory candidate 결손
- unsupported inference가 핵심 근거인 기억

Editor 검토 대기:

- `interpretation_risk='medium'`
- `unsupported_inferences`가 있는 기억
- `reflection_value='high'`이지만 근거가 단건인 후보
- 민감하거나 관계 해석이 포함된 후보

### 패턴/연결 후보 기준

- 근거 기억 1개: 패턴으로 부르지 않는다. `single_observation` 또는 `open_question`만 허용한다.
- 근거 기억 2개: 연결 후보는 가능하지만 표현은 낮은 확신으로 쓴다.
- 근거 기억 3개 이상: 반복 패턴 후보 가능.
- primary evidence 없는 근거는 최종 인용에 쓰지 않는다.
- `memory_candidate`는 탐색 보조로만 쓰고 최종 근거는 conversation 원문으로 돌아간다.

### 발행 전 금지 기준

다음 후보는 발행하지 않는다.

- 재미는 있으나 근거가 약한 후보
- 사용자 성격, 심리, 성장 서사를 단정하는 후보
- 반례 확인 없이 장기 패턴으로 확장한 후보
- `high` risk 기억을 핵심 근거로 삼은 후보
- 조언, 처방, 자기계발 결론으로 끝나는 초안
- 알림 문구가 사용자를 평가하거나 회고 과제로 압박하는 경우

---

## 다음 실행 권장

1. legacy schema 4건을 `legacy_schema=true` 또는 별도 리스트로 분리한다. 2026-07-09 사용자 확인을 거쳐 4건 모두 `schema_version=2`로 보강 완료했다.
2. `reflection_seed_candidate`는 현재 boolean 채움률이 낮으므로, 당분간 `memory_type`, `reflection_value`, `key_phrases`, `emerging_themes` 조합으로 대체한다.
3. Reporter POC는 `low risk + current schema + primary evidence + reflection_value medium/high` 기억만 대상으로 시작한다.
4. 후보 20개를 만들되, 근거 기억 1개 후보는 패턴 카드가 아니라 단일 관찰 카드로 제한한다.
5. 후보 평가 결과는 기존 `reflection_evaluations`에 억지로 넣지 말고, 새 `content_evaluations` 설계 전까지 별도 JSONL/Markdown으로 기록한다.
6. Reporter POC 후 `content_evaluations` 테이블을 추가할지 결정한다.

---

## 사용자 직접 검토 보완 로그

### 2026-07-09 legacy schema 보강

사용자 확인을 거쳐 legacy schema 4건을 최신 기억 구조로 보강했다.

| 항목 | 결과 |
|---|---:|
| `schema_version=2` | 105/105 |
| `event_summary` 채움 | 105/105 |
| `memory_candidate` 채움 | 105/105 |
| primary evidence 존재 | 105/105 |
| `interpretation_risk` 채움 | 105/105 |

### 2026-07-09 장기 재료 납득성 검토

| 기억 ID | 기존 주제 | 사용자 판정 | 반영 |
|---|---|---|---|
| `587c9c03-ca15-4f98-a99b-c82132183fbc` | 조직 개편과 경쟁에 대한 걱정 | `revise` | 특정 조직개편보다 "직장과 조직 생활 속 인간관계 긴장"이 더 적절하다는 사용자 피드백을 반영했다. `topic`, `memory_candidate`, `raw_memory.emerging_themes`를 수정하고 `interpretation_risk=medium`은 유지했다. |
| `52f044e5-170b-4eff-bf55-ea1a87ffd7c9` | 팀장과의 대화 | `postpone` | 지난 1년간 팀장과의 대화·관계가 장기 주제였던 것은 맞지만, 2주 후 팀장이 바뀌면 지속 여부가 달라질 수 있다는 사용자 피드백을 반영했다. `raw_memory.long_term_material_review`, `raw_memory.reporter_candidate_status=postpone`, `raw_memory.next_review_trigger`를 추가했다. 새 팀장 이후에도 반복되면 "상사와의 대화 긴장"으로 keep하고, 사라지면 과거 맥락 자료로만 사용한다. |
| `c75ff5c8-0bea-4aac-ac58-abd5cf1ed922` | 부서 내 관계 | `revise` | 장기 재료는 맞지만 "직장과 조직 생활 속 인간관계 긴장"과 겹치는 영역이 있다는 사용자 피드백을 반영했다. 독립 Reporter 후보가 아니라 상위 주제의 근거 기억으로 쓰도록 `raw_memory.reporter_candidate_status=supporting_evidence`, `raw_memory.parent_theme`, `raw_memory.failure_type_if_separate=DUPLICATED_CARD`를 추가했다. |
| `241f6fde-3482-4038-83ac-992fa65568f3` | 텔레그램 대화 메모리 프로젝트 | `keep` | 프로젝트 자체의 의의와 북극성을 직접 설명하는 기억으로 사용자 확인을 받았다. `raw_memory.reporter_candidate_status=keep`, `raw_memory.candidate_role=project_north_star`로 표시했다. |
| `2bce79a0-3839-45ee-b2ce-78077e65ccb0` | 직장 내 관계와 스트레스 | `revise` | "직장과 조직 생활 속 인간관계 긴장", "부서 내 관계"와 연관이 깊다는 사용자 피드백을 반영했다. 독립 후보가 아니라 상위 주제의 핵심 근거로 쓰도록 `raw_memory.reporter_candidate_status=core_evidence`, `raw_memory.parent_theme`, `raw_memory.linked_supporting_memory`, `raw_memory.failure_type_if_separate=DUPLICATED_CARD`를 추가했다. |
| `4ecb2bbf-266c-4e02-98dc-ddf311635719` | 공무원 업무에 대한 불만 | `keep` | 공공조직의 형식적 보고와 이미 정해진 결론을 문서 절차로 반복하는 불만을 보여주는 독립 주제로 유지한다. `raw_memory.reporter_candidate_status=keep`, `raw_memory.candidate_role=public_work_formality_frustration`로 표시했다. |
| `90755251-dc8f-472d-982e-59ed9e11dcce` | 자신에 대한 탐구와 부끄러움 | `keep` | 자기탐구가 지속되는 관심사이면서, 그것을 드러내는 데 대한 부끄러움과 사회적 기준 의식이 함께 드러나는 독립 주제로 유지한다. `raw_memory.reporter_candidate_status=keep`, `raw_memory.candidate_role=self_inquiry_and_embarrassment`로 표시했다. |
| `7c8a298c-a65f-49b6-b80d-475cbe5661cb` | 한나 아렌트와 사회적 차별 | `postpone` | 한나 아렌트 책은 다 읽어서 당분간 직접 언급 가능성이 낮지만, 사회적 차별에 대한 생각은 앞으로 나올 가능성이 조금 있다는 사용자 피드백을 반영했다. `raw_memory.reporter_candidate_status=postpone_low_priority`, `raw_memory.candidate_role=possible_future_theme`, `raw_memory.next_review_trigger`를 추가했다. 사회적 차별·소수자성 관련 주제가 다시 나오면 keep으로 재평가한다. |
| `bbe52004-8229-475e-ab7c-0f6f233b64d1` | 자기 비판 | `keep` | 자기비판과 걱정이 즐거워했던 일까지 손에 잡히지 않게 만드는 흐름을 보여주는 독립 재료로 유지한다. `raw_memory.reporter_candidate_status=keep`, `raw_memory.candidate_role=self_criticism_blocks_joy`로 표시했다. |
| `252b3f93-c01d-42d9-9f32-7ce37393ad9b` | 자아와 외부환경에 대한 성찰 | `postpone` | 자아, 알아차림, 외부환경의 영향이라는 주제는 장기 재료 가능성이 있지만 `interpretation_risk=medium`이고 관련 기억이 더 쌓인 뒤 연결 후보로 재평가하는 편이 적절하다고 정리했다. `raw_memory.reporter_candidate_status=postpone`, `raw_memory.candidate_role=needs_more_evidence`, `raw_memory.next_review_trigger`를 추가했다. |
| `47b3f478-7492-4e2c-b559-636b046a18cf` | 알아차림 | `postpone` | 알아차림의 어려움, 명상, 주변 자극과 감정의 영향이라는 주제는 장기 재료 가능성이 있지만 관련 기억이 더 반복된 뒤 연결 후보로 재평가하는 편이 적절하다고 정리했다. `raw_memory.reporter_candidate_status=postpone`, `raw_memory.candidate_role=needs_more_evidence`, `raw_memory.parent_theme`, `raw_memory.next_review_trigger`를 추가했다. |
| `91c3ca8e-3a43-464e-8bb2-73d99370d228` | 자기 비하와 승진에 대한 감정 | `keep` | 승진 속도, 타인의 평가, 부끄러움, 자기비하로 넘어가지 않기 위한 방지턱이라는 감정 구조가 장기 재료로 중요하다는 사용자 판정을 반영했다. 단, `interpretation_risk=medium`이므로 `raw_memory.reporter_candidate_status=keep_needs_editor_review`, `raw_memory.editor_review_reason=interpretation_risk_medium`으로 표시했다. |
| `cbab7fe4-8f82-4125-a4a3-ae47865c64e1` | 엄마와의 성격 닮음 | `keep` | 엄마와의 성격 유사성, 가족 관계 속 자기 이해, 편한 사람 앞에서 웃기고 싶어하는 감각이 함께 드러나는 독립 장기 재료로 유지한다. `raw_memory.reporter_candidate_status=keep`, `raw_memory.candidate_role=family_similarity_and_humor_self_image`로 표시했다. |
| `73c6940a-c4fd-487f-a140-f038641423a7` | 상사와 책임 | `keep` | 마땅히 해야 하는 판단조차 하지 않는 과장과 올해 계속 같이 있을 예정이라는 사용자 피드백을 반영했다. 상사의 권한과 책임 회피, 하급자에게 부담을 넘기는 모습, 그 모습과 자신을 비교하며 느끼는 수치심과 되고 싶은 인간상이 함께 드러나는 장기 재료로 유지한다. 단, `interpretation_risk=medium`이므로 `raw_memory.reporter_candidate_status=keep_needs_editor_review`, `raw_memory.editor_review_reason=interpretation_risk_medium`으로 표시했다. |
| `092720f1-a72e-4afd-a9d8-e7a5dc90ba47` | 인간상 | `keep` | 다른 사람들에게 보일 모습과 평가에 신경쓰지 않는 사람이 되고 싶다는 인간상은 자기비하, 승진 감정, 타인의 평가와 연결되는 기본 장기 주제로 유지한다. `raw_memory.reporter_candidate_status=keep`, `raw_memory.candidate_role=desired_self_less_bound_by_evaluation`으로 표시했다. |

### 사용자 직접 검토 최종 집계

장기 재료 검토 범위는 `memory_type='reflection_seed'` 또는 `reflection_value='high'`인 15건으로 잡았다. 2026-07-09에 사용자 직접 검토를 모두 완료했다.

| 항목 | 건수 |
|---|---:|
| 검토 대상 | 15 |
| 사용자 검토 완료 | 15 |
| `keep` | 8 |
| `revise` | 3 |
| `postpone` | 4 |

Reporter 후보 상태별 분포는 다음과 같다.

| `reporter_candidate_status` | 건수 | 의미 |
|---|---:|---|
| `keep` | 6 | 독립 Reporter 후보로 유지 가능 |
| `keep_needs_editor_review` | 2 | 유지하되 Editor 검토 필요 |
| `parent_theme` | 1 | 상위 주제 |
| `core_evidence` | 1 | 상위 주제의 핵심 근거 |
| `supporting_evidence` | 1 | 상위 주제의 보조 근거 |
| `postpone` | 3 | 추가 기억 후 재평가 |
| `postpone_low_priority` | 1 | 낮은 우선순위 보류 |

사용자 검토 후 1단계의 `seed 후보 중 장기 재료 납득률`은 다음처럼 본다.

- 넓은 의미의 장기 재료 인정: `keep + revise + postpone = 15/15`
- 즉시 또는 조건부 활용 가능: `keep + revise = 11/15`
- 독립 후보로 바로 유지 가능: `reporter_candidate_status=keep` 6/15
- Editor 검토 포함 유지 가능: `keep + keep_needs_editor_review + parent_theme + core_evidence + supporting_evidence` 11/15

### 2026-07-09 fidelity 신호 기준 백필 1차

사용자 설명에 따라 `reflection_seed_signal`, `oriented_marker`, `human_ideal_marker`는 DB 필드가 아니라 `fidelity.py`의 판정 신호로 해석했다. 따라서 새 marker 필드를 추가하지 않고, 확장된 신호 기준으로 과거 기억의 공식 필드만 보강했다.

1차 배치에서는 신호가 강한 과거 기억 10건을 사용자 승인 후 반영했다.

반영한 필드:

- `raw_memory.memory_type`
- `raw_memory.reflection_value`
- `raw_memory.reflection_seed_candidate`
- `raw_memory.temporal_status`
- `raw_memory.value_tags`
- `raw_memory.projects`
- top-level `projects`

수정하지 않은 필드:

- `event_summary`
- `memory_candidate`
- `conversation`

1차 백필 후 집계:

| 항목 | 반영 후 |
|---|---:|
| 1차 백필 반영 건수 | 10 |
| `temporal_status` 보유 기억 | 23/105 |
| `reflection_seed_candidate` 보유 기억 | 23/105 |
| `value_tags` 보유 기억 | 23/105 |
| `reflection_seed_candidate=true` | 10 |
| `memory_type=reflection_seed` | 20 |
| `reflection_value=high` | 9 |

관련 문서: `docs/backfill_batch_1_proposal.md`

---

## 결론

0단계는 통과다. 기존 평가 로그와 Supabase mirror 구조는 장기 콘텐츠 평가 체계로 이어 붙일 수 있다.

1단계는 사용자 직접 검토 보완 후 통과로 상향한다. 현재 105개 기억은 모두 `schema_version=2`이고, `event_summary`, `memory_candidate`, primary evidence, `interpretation_risk`가 105/105로 채워져 있다. 장기 재료 검토 대상 15건도 모두 사용자 확인을 마쳤으며, 이 중 11건은 즉시 또는 조건부로 Reporter 후보 체계에 활용 가능하다. 다만 장기 비전의 핵심인 "스스로 읽을 만한 콘텐츠를 준비하는 에이전트"로 가려면, 앞으로 새 기억 저장 단계에서 `reflection_seed_candidate`, `value_tags`, `temporal_status`, `open_questions` 같은 장기 분석 필드를 더 안정적으로 남겨야 한다.
