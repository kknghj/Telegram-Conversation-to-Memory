# Validation Plan

## 현재 검증 상태

- 기준일: 2026-07-16
- 0단계 평가 기반 정리 — `passed` (근거: `docs/validation_stage_0_1_decisions.md`, 2026-07-09)
- 1단계 기억 기질 품질 — `passed` (근거: 105개 기억 및 사용자 직접 검토, `docs/validation_stage_0_1_decisions.md`, 2026-07-09)
- 2단계 회고 씨앗 수집 — `conditional_pass` (근거: 07-09~pre-luna mini live 22건 — 재료 풍부 16/17·피로 4/17·코칭톤 잔존; seed 후보 사용자 납득 6/7로 품질 축 보강, `reports/validation/stage2_window_20260709_pre_luna.md`·`stage2_seed_review_20260709_pre_luna.json`, 2026-07-16. luna live 종결 관찰 미완)
- 3단계 Reporter 후보 발견 — `passed` (근거: 20개 후보 사용자 전수 검토, `data/evaluation/reporter_poc_2026-07-11.json`, 2026-07-11)
- 4단계 Style Editor 후킹/재미 — `conditional_pass` (근거: 10개 후보 사용자 전수 검토, 관찰형·후킹형 선호 9/10, 최종 `too_much` 0/10, `taste_fit=high|medium` 9/10, `data/evaluation/style_editor_poc_2026-07-11.json`, 2026-07-11. 다음 라운드의 `HOOK_TOO_FLAT` 감소 여부는 미검증)
- 현재 검증 단계: **2단계 회고 씨앗 수집 — `conditional_pass`**
- 다음 검증 행동: `gpt-5.6-luna` live에서 질문 포함 세션 10건 이상을 모은 뒤, 코칭톤·패스/피로·`open_questions`/`reflection_seed` 채움·중복/저중요도 앵커 재발을 재검증한다.
- 진입 제한: 질문률을 코드로 강제하지 않으며, `question_outcome` trace로 생성/거절 사유만 관측한다. 모델 비교 runner는 평가 전용이며 production drafts/memory에 쓰지 않는다.

이 블록은 검증 진도의 단일 요약이다. 새 증거가 생기면 상태, 근거, 날짜, 다음 검증 행동을 함께 갱신하며 다음 검증 행동은 항상 하나만 유지한다.

### 2026-07-16 2단계 mini 구간 live 평가 (07-09 → pre-luna)

- 목적: 후속 질문 복구(07-09) 이후·luna 전환 이전 `gpt-4o-mini` 신규 기억으로 2단계 통과 기준 채점
- 표본: 승인 기억 22건, 질문 포함 세션 17건(대화 assistant turn 기준), 질문 없음 5건
- 통과 기준:
  - 재료 풍부화 ≥60% — **pass** 16/17 (94%)
  - 거부/피로 ≤20% — **fail** 4/17 (24%: `패스` 3 + 명시 불만 1)
  - `meaning_check` 반복 실패 0 — **fail** (도스토옙스키 재질문, `interpretation_failures.redundant_question`)
  - 부정 감정 직후 긍정 회상 실패 0 — **pass**
  - 별로인 질문 유형 감소 — **partial** (07-12 이후 redundant/low_salience 재발 없음, 코칭톤 6/17 잔존)
- 씨앗 필드: `key_phrases` 22/22, `open_questions` 0/22, `reflection_seed` 본문 0/22, `reflection_seed_candidate` 7/22(플래그만)
- seed 후보 사용자 검토: 납득 6 / 아님 1 (86% ≥70%) — **품질 축 pass**. S6(겸직 허가)만 제외. S7: 원문에 생산성 언급이 있으면 seed로 남겨도 코칭으로 보지 않음
- 판정: 구간 평가 `conditional_pass` 유지 — seed *후보 품질*은 보강됐으나 페이로드 공란·피로·코칭톤·meaning_check 실패로 `passed` 불가. luna live 종결은 별도
- 보고서: `reports/validation/stage2_window_20260709_pre_luna.md`, `reports/validation/stage2_seed_review_20260709_pre_luna.json`

### 2026-07-16 운영 모델 확정: gpt-5.6-luna

- 목적: 요약·태깅·첫 후속 질문 품질을 동일 규칙으로 비교해 Archivist/질문 경로 운영 모델 결정
- 근거: `run_20260715_seed` 사람 평가 30건 — luna wins 17 / terra 5 / mini 0 / tie 8; fidelity·interpretation·question 평균 모두 luna 1위; over_interpretation 0
- 비용: luna ≈ $0.015/case (mini $0.001, terra $0.033) — 품질 대비 수용
- 판정: 운영 모델 결정 `passed` (incident: `docs/archive/incidents/model_selection_gpt56_luna_2026-07-16.md`). Phase 2 전체는 live 관찰 전까지 `conditional_pass` 유지
- 저장소 조치: `OPENAI_MODEL` 기본값·`render.yaml`·문서 기본값을 `gpt-5.6-luna`로 전환. Render Dashboard env는 배포 시 수동 확인 필요

### 2026-07-15 프롬프트 감사·모델 비교 평가 도구

- 목적: 질문·해석 규칙 중복/충돌 정리 후, 동일 사례·동일 규칙으로 `gpt-4o-mini` / `gpt-5.6-luna` / `gpt-5.6-terra`를 공정 비교
- 산출물: `reports/prompt_audit/`, `docs/model_comparison_experiment.md`, `conversation_to_memory/evaluation/`
- 데이터셋: Supabase `drafts` 읽기 전용 추출 `ds_20260715_seed` (30건, seed=20260715, saved 29 / cancelled 1). 원문 `cases.jsonl`은 gitignore
- 모델 접근: 세 모델 모두 probe `ok=True` (동일 `OPENAI_API_KEY`)
- 실행: `reports/model_comparison/run_20260715_seed` — 90/90 성공 (초안+첫 질문). GPT-5 계열 초기 빈 응답은 `max_completion_tokens` 확대 후 재실행으로 해소
- 자동 검증: `pytest -q` 313 passed, 1 skipped (`model_comparison_live`)
- 판정: 도구·규칙 정리·배치 실행은 완료. 사람 블라인드 평가·운영 모델 결정은 2026-07-16에 완료(위 항목)
- 문서: `docs/model_comparison_experiment.md`
- 비교 화면: `reports/model_comparison/run_20260715_seed/comparison.html`

### 2026-07-12 질문 품질·피드백 오염 수정

- 실패 사례 A: 도스토옙스키 연결 재질문 → `redundant_question` / `answered_already` 차단
- 실패 사례 B: 콩국수 저중요도 앵커·추상화 불일치·메타 피드백 원문 유입·GPT people 오분류
- 구현: archive_gap/reflective_handle 분리, 후보 검증, 후속 응답 분류, 두 번째 질문 게이트, people/projects/tools/events 후처리
- 자동 검증: `python -m pytest -q` 287 passed
- fixture replay: `tests/test_question_quality_replay.py` passed
- failure dataset: `telegram_20260712_dostoevsky_redundant_question`, `telegram_20260712_summer_menu_low_salience_anchor`
- 판정: `conditional_pass` — 코드/테스트는 통과, live 20건 관찰 전
- incident: `docs/archive/incidents/question_quality_and_feedback_contamination_2026-07-12.md`

### 2026-07-11 Editor 근거·반례 수동 POC 중간 결과

- 사용자 직접 검토: 5개
- `ready_for_draft`: 3개
- `ready_for_draft` 중 추가 근거가 쌓일 때까지 `maturation_hold`: 2개
- 즉시 내부 초안화 가능: 1개
- `needs_more_evidence`: 2개
- 보류 또는 폐기 비율: 40%
- ready 후보 중 근거 기억 2개 이상: 3/3 (100%)
- 확인된 편집 경계:
  - 편의성 발언과 제품 윤리 발언을 곧바로 하나의 가치관으로 합치지 않는다.
  - 불안 감소의 원인을 불확실성 해소 하나로 고정하지 않는다.
  - 비슷한 책의 연결은 현재 읽는 장르와 알림 시점이 맞지 않으면 보류한다.
  - 업무 진척의 만족을 본업 선호로 확대하지 않는다.
- 5단계 판정: `conditional_pass` — 보류율과 근거 수 기준은 충족했으나 최소 검증 단위 20개 중 5개만 검토했다.
- 근거 기록: `data/evaluation/editor_poc_2026-07-11.json`

### 2026-07-11 Style Editor 수동 POC 결과

- Reporter 후보 선정 및 사용자 검토: 10개
- 사실형보다 관찰형 또는 후킹형이 선택된 후보: 9개 (90%)
- 최종 문장 `too_much=true`: 0개 (0%)
- `taste_fit=high|medium`: 9개 (90%)
- 사용자가 실제로 재미 또는 웃음을 확인한 후보: 2개
- 운영 판정: keep 9개, postpone 1개
- 확인된 실패: 직관적이지 않은 비유, 긴 호흡과 과도한 설명, 근거 제한 문구로 약해진 후킹
- 보류 후보: 예상 밖의 발견 후보는 두 장면만으로 일반화를 피하면 문장이 구구절절해져 추가 근거가 쌓일 때까지 `postpone`
- 4단계 판정: `conditional_pass` — 선호, 과장 억제, 취향 적합성의 핵심 기준은 통과했으나 `HOOK_TOO_FLAT` 피드백이 다음 라운드에서 감소하는지는 아직 확인할 수 없다.
- 근거 기록: `data/evaluation/style_editor_poc_2026-07-11.json`

### 2026-07-11 Reporter POC 시작 증거

- Supabase 승인 기억: 112개
- `schema_version=2`: 112개
- Reporter 자동 진입 기준 충족: 67개
- 위험도 분포: low 101개, medium 10개, high 1개
- 회고가치 분포: low 26개, medium 77개, high 9개
- 생성 및 사용자 검토 완료: 20개
- 사용자 Reporter 판정: accepted 16개, revise 4개, discard 0개
- `accuracy=correct|partial`: 19개
- `interesting=true`: 16개
- `revisit=true`: 19개
- 운영 판정: keep 10개, revise 7개, postpone 2개, discard 1개
- 실패 유형: `BORING_BUT_TRUE` 2개, `OVER_GENERALIZATION` 1개, `DATA_INSUFFICIENT` 2개, `OBVIOUS_INSIGHT` 1개
- `fun=true`: 1개, `FUN_BUT_UNGROUNDED`: 0개
- 3단계 판정: `passed` — 정확성·흥미·재독 기준을 모두 충족했고 일반화 위험 후보는 수정·보류·폐기로 격리했다.
- 근거 기록: `data/evaluation/reporter_poc_2026-07-11.json`

## 목적

이 문서는 Conversation-to-Memory가 기억 기반 개인 AI 에이전트라는 북극성에 도달하기 위해, 앞으로 차례로 검증해야 할 최소 단위와 통과 기준을 정의한다.

제품의 장기 목표는 단순히 정확한 기억을 저장하는 것이 아니라, 사용자의 장기 기억을 바탕으로 **흥미롭고, 재미있고, 다시 읽고 싶은 콘텐츠를 스스로 준비하는 에이전트**가 되는 것이다.

따라서 검증은 두 축을 동시에 다룬다.

```text
1. 맞는가?       원문 근거, 과해석 방지, 신뢰성
2. 읽고 싶은가?  후킹, 재미, 취향 적중, 다시 읽기 욕구
```

정확하지만 밋밋한 콘텐츠는 아직 성공이 아니다. 재미있지만 근거가 약한 콘텐츠도 성공이 아니다.

---

## 선행 자료

현재 저장소에는 이미 초기 MVP 평가 자료가 있다.

| 자료 | 의미 |
|------|------|
| `data/evaluation/reflection_failures.jsonl` | 36건 단계의 초기 회고 실패/성공 로그 |
| `data/evaluation/mvp_round2_2026-06-19.json` | 50건 단계 MVP 2차 평가 |
| `data/evaluation/mvp_round3_2026-07-04.json` | 88건 단계 MVP 3차 평가 |
| `data/evaluation/reflection_evaluations.jsonl` | 패턴 카드별 사용자 평가 로그 |
| `docs/reflection_evaluation.md` | primary evidence, failure taxonomy, sample size 기준 |
| `docs/evaluation_supabase_integration.md` | 평가 로그 Supabase mirror 구조 |

이 자료에서 이미 확인된 중요한 교훈은 다음과 같다.

- 36건 단계는 최종 성능 평가보다 실패 유형 탐색에 적합하다.
- 50건 단계에서는 일부 패턴과 새로운 관점이 사용자에게 인정되기 시작했다.
- 88건 단계에서는 패턴 카드 5건 중 accepted 3건, partial 1건, rejected 1건이 나왔다.
- 틀린 해석은 대부분 근거 약함, 과확장, 피상적 연결에서 발생했다.
- 질문 품질은 별도 축으로 관리해야 한다.
- `interesting`, `revisit`, `accuracy`, `evidence`, `action`은 앞으로도 유지할 만한 평가 필드다.

---

## 전체 검증 순서

```text
0. 평가 기반 정리
1. 기억 기질 품질 검증
2. 회고 씨앗 수집 검증
3. Reporter 후보 발견 검증
4. Style Editor 후킹/재미 검증
5. Editor 근거·반례 검증
6. Draft 읽기 경험 검증
7. Editor-in-Chief 발행 판단 검증
8. Telegram 알림/피드백 검증
9. 장기 개인화 검증
10. 반자동 운영 검증
```

각 단계는 이전 단계의 산출물을 전제로 한다. 단, 일부 단계는 수동 실험으로 먼저 검증한 뒤 구현해도 된다.

---

## 공통 평가 필드

앞으로의 모든 콘텐츠 후보, 초안, 발행물 평가는 최소한 다음 필드를 남긴다.

```json
{
  "evaluation_id": "",
  "evaluated_at": "",
  "memory_count": 0,
  "period_start": "",
  "period_end": "",
  "item_id": "",
  "item_type": "candidate | hook | draft | published_content",
  "accuracy": "correct | partial | wrong | not_applicable",
  "evidence": "sufficient | weak | wrong | not_applicable",
  "interesting": true,
  "fun": true,
  "revisit": true,
  "taste_fit": "high | medium | low | unknown",
  "too_much": false,
  "action": "keep | revise | discard | postpone",
  "failure_type": null,
  "user_comment": ""
}
```

### 필드 의미

| 필드 | 의미 |
|------|------|
| `accuracy` | 사용자가 보기에도 맞는 해석인가 |
| `evidence` | 원문·승인 기억 근거가 충분한가 |
| `interesting` | 흥미로운 관점인가 |
| `fun` | 작게라도 재미, 위트, 문장 맛이 있는가 |
| `revisit` | 나중에 다시 읽고 싶은가 |
| `taste_fit` | 사용자의 취향 유머와 톤에 맞는가 |
| `too_much` | 과장, 캐릭터화, 놀림, 단정이 선을 넘었는가 |
| `action` | 유지, 수정, 폐기, 보류 중 무엇인가 |
| `failure_type` | 실패 유형 분류 |

---

## Failure Taxonomy 확장

기존 `docs/reflection_evaluation.md`의 실패 유형을 유지하고, 콘텐츠 발행 단계에 필요한 유형을 추가한다.

| 유형 | 의미 |
|------|------|
| `SEARCH_FAILURE` | 관련 기록을 찾지 못함 |
| `CONNECTION_FAILURE` | 관련 기록은 있으나 연결 이유가 피상적 |
| `INTERPRETATION_FAILURE` | 근거보다 의미를 크게 확대 |
| `OBVIOUS_INSIGHT` | 맞지만 너무 뻔함 |
| `OVER_GENERALIZATION` | 적은 사례를 성향으로 일반화 |
| `DATA_INSUFFICIENT` | 현재 데이터로 판단 불가 |
| `DUPLICATED_CARD` | 비슷한 카드 중복 |
| `HOOK_TOO_FLAT` | 정확하지만 열어보고 싶지 않음 |
| `HOOK_TOO_MUCH` | 재미를 위해 과장·단정·놀림이 선을 넘음 |
| `TASTE_MISMATCH` | 사용자의 취향과 맞지 않는 유머·비유·문체 |
| `BORING_BUT_TRUE` | 맞지만 콘텐츠로서 매력이 낮음 |
| `FUN_BUT_UNGROUNDED` | 재미는 있으나 근거가 약함 |
| `PUBLISHING_FATIGUE` | 내용은 괜찮지만 빈도·타이밍이 부담스러움 |

---

## 0단계. 평가 기반 정리

**목적**  
기존 MVP 평가와 앞으로의 검증을 같은 체계로 이어 붙인다.

**최소 검증 단위**

- 기존 `data/evaluation` 자료를 기준으로 평가 필드와 실패 유형 정리
- 36건, 50건, 88건 평가에서 유지할 지표와 버릴 지표 구분
- Supabase mirror가 필요하면 기존 평가 테이블에 장기 콘텐츠 평가를 확장할지 별도 테이블을 둘지 결정

**지금 가능한가**  
가능하다. 현재 자료만으로도 충분하다.

**통과 기준**

- 기존 평가 로그를 새 단계 평가와 연결할 수 있다.
- `accuracy`, `evidence`, `interesting`, `revisit`, `action` 필드는 유지된다.
- 재미/후킹 평가를 위해 `fun`, `taste_fit`, `too_much` 필드가 추가된다.

---

## 1단계. 기억 기질 품질 검증

**목적**  
축적된 기억이 장기 콘텐츠 생성의 재료로 쓸 수 있는지 확인한다.

**최소 검증 단위**

- 승인 기억 100건 내외 표본 평가
- 필드 채움 상태와 근거 품질 집계
- high-risk 기억과 legacy schema 기억 분리

**적절한 시점**

- 50건: 초기 데이터 건강성 점검
- 100건: 첫 정식 품질 평가
- 이후 250건, 500건 단위로 재평가

**평가 항목**

- `event_summary` 품질
- `memory_candidate`의 원문 충실도
- `conversation` primary evidence 존재 여부
- `key_phrases` 채움률
- `emerging_themes` 채움률
- `open_questions` 채움률
- `reflection_seed_candidate` 품질
- `interpretation_risk` 분포
- `schema_version` 분포

**통과 기준**

- primary evidence rate 95% 이상
- `schema_version` 최신 비율 95% 이상
- `event_summary`와 `memory_candidate`가 비어 있거나 무의미한 기록 5% 이하
- `key_phrases` 또는 `emerging_themes` 중 하나 이상 채워진 기록 60% 이상
- `reflection_seed_candidate`로 표시된 기억 중 사용자 검토 시 70% 이상이 장기 재료로 납득됨
- high-risk 해석이 콘텐츠 후보에 자동으로 진입하지 않음

---

## 2단계. 회고 씨앗 수집 검증

**목적**  
기억 저장 단계에서 나중에 콘텐츠가 될 만한 재료가 충분히 남는지 검증한다.

**최소 검증 단위**

- 최근 30개 신규 기억을 대상으로 회고 씨앗 필드 평가
- 질문이 있었던 세션과 없었던 세션 비교
- 질문 품질 실패 로그 점검

**적절한 시점**

- `REFLECTION_AGENT_ENABLED`가 켜진 뒤 최소 20세션
- 질문 포함 세션 10건 이상
- 전체 승인 기억 100건 이상이면 첫 평가 가능

**평가 항목**

- 질문이 기록을 풍부하게 만들었는가
- 질문이 코칭처럼 느껴졌는가
- `open_questions`가 실제 사용자 질문을 잘 담았는가
- `reflection_seed`가 사건보다 가치관·판단 기준을 잘 포착했는가
- 피로 신호 후 추가 질문이 중단되었는가

**통과 기준**

- 질문 포함 세션 중 60% 이상에서 기억 재료가 더 풍부해짐
- 질문 거부/피로 신호 발생률 20% 이하
- `meaning_check` 반복 실패 0건
- 부정 감정 직후 긍정 회상 질문 실패 0건
- 사용자가 "이 질문은 별로"라고 판단한 질문 유형은 다음 라운드에서 감소

---

## 3단계. Reporter 후보 발견 검증

**목적**  
기억에서 흥미로운 연결 후보를 많이 발견할 수 있는지 검증한다.

**최소 검증 단위**

- 승인 기억 전체 또는 최근 100건으로 후보 20개 생성
- 후보마다 근거 기억, 연결 유형, 흥미 포인트, 불확실성 기록

**적절한 시점**

- 100건: 첫 Reporter POC
- 250건: 반복 주제·프로젝트 흐름 검증
- 500건: 장기 변화와 계절성 후보 검증

**후보 유형**

- 반복 표현
- 반복 가치관
- 프로젝트 흐름
- 관계 패턴
- 장면/감각의 재등장
- 열린 질문의 재등장
- 오래된 기억과 최근 기억의 대비

**통과 기준**

- 후보 20개 중 8개 이상이 `accuracy=correct` 또는 `partial`
- 후보 20개 중 6개 이상이 `interesting=true`
- 후보 20개 중 4개 이상이 `revisit=true`
- `FUN_BUT_UNGROUNDED` 후보는 0건 또는 즉시 폐기됨
- 근거 기억 1개뿐인 후보는 패턴으로 단정하지 않음
- 사용자가 accepted/revise/discard를 판단할 수 있을 만큼 근거가 표시됨

---

## 4단계. Style Editor 후킹/재미 검증

**목적**  
같은 근거를 더 궁금하고 재미있게 표현할 수 있는지 검증한다.

**최소 검증 단위**

- Reporter 후보 10개 선택
- 각 후보마다 제목 또는 첫 문장 3종 생성
  - 사실형
  - 관찰형
  - 후킹형
- 사용자가 가장 읽고 싶은 문장, 선을 넘은 문장, 취향에 맞는 문장을 고름

**적절한 시점**

- Reporter 후보가 20개 이상 안정적으로 생성된 뒤
- 기억 100건에서도 가능하지만, 250건 이상이면 취향 패턴 판단이 더 안정적
- 사용자의 명시적 유머/문체 피드백이 20건 이상 쌓이면 개인화 검증 가능

**통과 기준**

- 후보 10개 중 5개 이상에서 후킹형 또는 관찰형이 사실형보다 선택됨
- `too_much=true` 비율 20% 이하
- `taste_fit=high` 또는 `medium` 비율 60% 이상
- `HOOK_TOO_FLAT` 피드백이 다음 라운드에서 감소
- 웃기지만 근거 약한 문장은 `FUN_BUT_UNGROUNDED`로 폐기됨

**주의 기준**

재미는 근거 기준을 낮추는 면허가 아니다. Style Editor는 표현을 바꿀 수 있지만 사실, 감정, 성격을 새로 만들 수 없다.

---

## 5단계. Editor 근거·반례 검증

**목적**  
Reporter 후보를 바로 발행하지 않고, 근거와 반례를 검토해 초안화할 후보를 고른다.

**최소 검증 단위**

- Reporter 후보 20개를 Editor가 검토
- 각 후보에 `ready_for_draft`, `needs_more_evidence`, `reject` 판정 부여
- 반례 또는 조심할 점을 최소 1개 이상 검토

**적절한 시점**

- Reporter 후보 평가에서 `interesting=true` 후보가 6개 이상 나오는 시점
- 100건부터 가능
- 반례 탐색은 250건 이상에서 더 의미 있음

**통과 기준**

- 후보 중 최소 30%는 보류 또는 폐기됨
- `interpretation_risk=high` 후보는 바로 초안화하지 않음
- `evidence=weak` 후보는 `needs_more_evidence` 또는 `revise`로 이동
- accepted 후보의 80% 이상이 근거 기억 2개 이상 보유
- 사용자가 폐기 판단을 납득할 수 있음

---

## 6단계. Draft 읽기 경험 검증

**목적**  
검토된 후보가 실제로 읽을 만한 짧은 콘텐츠가 되는지 검증한다.

**최소 검증 단위**

- `ready_for_draft` 후보 5개로 짧은 초안 생성
- 각 초안은 제목, 본문, 근거 기억, 해석 위험도를 포함
- 사용자에게 발행하지 않고 내부 미리보기로 평가

**적절한 시점**

- Editor가 초안화 가능 후보를 5개 이상 만든 뒤
- 100건부터 가능
- 250건 이상이면 더 긴 서사형 초안 검증 가능

**통과 기준**

- 초안 5개 중 3개 이상이 `accuracy=correct` 또는 `partial`
- 초안 5개 중 2개 이상이 `interesting=true`와 `revisit=true`
- `too_much=true` 1건 이하
- 조언, 처방, 자기계발 결론 0건
- 원문 표현 또는 기억 근거가 본문에서 살아 있음
- 사용자가 "이건 내 기록을 멋대로 포장했다"고 느낀 초안은 폐기 또는 재작성

---

## 7단계. Editor-in-Chief 발행 판단 검증

**목적**  
좋은 초안이라도 지금 보여줄지, 보류할지 판단할 수 있는지 검증한다.

**최소 검증 단위**

- 초안 10개에 대해 발행 판단 부여
- `publish_now`, `postpone`, `do_not_publish` 중 하나 선택
- 알림 문구 1개 생성

**적절한 시점**

- 내부 초안이 10개 이상 쌓인 뒤
- 실제 Telegram 발행 전 필수
- 발행 이력이 10건 이상 생긴 뒤 기준 재평가

**통과 기준**

- 모든 초안이 즉시 발행되지 않음
- 비슷한 주제 연속 발행을 피함
- 민감하거나 해석 위험이 높은 콘텐츠는 보류됨
- 알림 문구가 낮은 압력, 낮은 단정, 높은 호기심을 유지함
- 사용자가 알림을 과제나 회고 요구로 느끼지 않음

---

## 8단계. Telegram 알림/피드백 검증

**목적**  
콘텐츠가 실제 알림으로 전달되었을 때, 사용자가 부담보다 호기심을 느끼는지 검증한다.

**최소 검증 단위**

- 수동 승인된 콘텐츠 5개만 Telegram으로 발행
- 각 콘텐츠에 간단한 피드백 버튼 또는 명령 제공
  - 읽음
  - 좋음
  - 나중에
  - 별로
  - 선 넘음
  - 근거 이상함

**적절한 시점**

- 내부 초안 검증에서 통과한 콘텐츠가 최소 5개 쌓인 뒤
- 처음에는 주 1회 이하 발행
- 10건 발행 후 첫 알림 경험 평가
- 30건 발행 후 빈도/피로도 평가

**통과 기준**

- 발행 10건 기준 open/read 반응 50% 이상
- `좋음` 또는 긍정 피드백 30% 이상
- `선 넘음` 또는 `근거 이상함` 10% 이하
- 같은 실패 유형이 2회 이상 반복되면 발행 기준 수정
- 알림 때문에 기록 행위 자체가 줄어들지 않음

---

## 9단계. 장기 개인화 검증

**목적**  
시간이 지날수록 콘텐츠가 더 개인적이고, 더 취향에 맞고, 더 읽을 만해지는지 검증한다.

**최소 검증 단위**

- 발행 콘텐츠 30건 이상
- 사용자 피드백 30건 이상
- 3개월 이상 기록 기간
- 취향/문체/유머 선호에 대한 가설 3개 생성 후 검증

**적절한 시점**

- 승인 기억 250건 이상
- 발행 콘텐츠 30건 이상
- 최소 3개월 이상 운영
- 장기 평가는 500건, 6개월 시점에서 더 의미 있음

**검증 항목**

- 사용자가 좋아한 후킹 방식이 반복적으로 재현되는가
- 싫어한 해석 방식이 줄어드는가
- 오래된 기억과 최근 기억의 연결이 더 자연스러워지는가
- 특정 프로젝트·관계·가치관의 변화가 보이는가
- 콘텐츠가 사용자에게 "나를 아는 느낌"을 주는가

**통과 기준**

- 최근 10개 발행물의 `taste_fit=high|medium` 비율 70% 이상
- 최근 10개 발행물의 `interesting=true` 비율 60% 이상
- `too_much=true` 비율 10% 이하
- 과거에 거부된 실패 유형의 재발률 감소
- 사용자가 "이건 예전보다 내 취향에 가까워졌다"고 판단하는 사례가 생김

---

## 10단계. 반자동 운영 검증

**목적**  
Reporter, Editor, Style Editor, Editor-in-Chief 흐름을 자동화하되, 최종 발행 품질을 유지하는지 검증한다.

**최소 검증 단위**

- 주 1회 백그라운드 작업
- 후보 생성 → 편집 검토 → 초안 생성 → 발행 후보 큐 적재
- 최종 발행은 수동 승인 유지

**적절한 시점**

- Reporter/Editor/Draft 검증이 각각 최소 2라운드 이상 통과한 뒤
- 발행 콘텐츠 10건 이상에서 심각한 실패가 없을 때
- 승인 기억 250건 이상이면 운영 효율 검증 가능

**통과 기준**

- 자동 생성 후보 중 20% 이상이 Editor 검토를 통과함
- Editor 통과 후보 중 30% 이상이 초안화 가능함
- 초안 중 20% 이상이 발행 후보가 됨
- 심각한 과해석 또는 근거 오류가 사용자에게 발행되지 않음
- 수동 검토 시간이 라운드당 줄어듦
- 자동화 이후에도 사용자 피로도와 부정 피드백이 증가하지 않음

---

## 데이터 규모별 추천 검증

| 데이터 규모 | 적합한 검증 | 부적합한 검증 |
|-------------|-------------|---------------|
| 30-50건 | 실패 유형 탐색, primary evidence 점검, 단일 관찰 카드 | 장기 성격·패턴 단정 |
| 50-100건 | 초기 패턴 카드, Reporter POC, 기억 기질 품질 평가 | 강한 장기 변화 서사 |
| 100-250건 | 후보 발견, 후킹 문장 실험, Editor 기준 수립, 내부 초안 | 완전 자동 발행 |
| 250-500건 | 개인화된 취향 검증, 반례 탐색, 프로젝트/관계 흐름 | 다중 사용자 일반화 |
| 500건 이상 | 장기 변화, 계절성, 발행 빈도 최적화, 반자동 운영 | 근거 없는 심리 분석 |
| 6개월 이상 | 시간에 따른 관점 변화, 오래된 기억 재발견 | 단기 반응만으로 품질 판단 |

---

## 단계 통과 원칙

다음 단계로 넘어가기 전에 항상 아래 질문에 답해야 한다.

1. 이 단계의 산출물은 사용자가 직접 평가했는가?
2. 맞는 것과 흥미로운 것을 별도로 기록했는가?
3. 재미있지만 근거 약한 산출물을 폐기했는가?
4. 정확하지만 밋밋한 산출물을 재작성 대상으로 표시했는가?
5. 실패 유형이 다음 프롬프트·규칙·편집 기준에 반영되었는가?
6. 아직 데이터가 부족한 판단을 보류했는가?

---

## 현재 시점의 권장 다음 검증

2026-07-09 기준 105개 기억에 대한 0-1단계 검증이 통과했으므로 다음 순서가 적절하다.

1. Reporter 후보 20개 생성
2. 후보 20개 중 사용자 평가로 accepted/revise/discard 기록
3. 상위 후보 10개에 대해 후킹 문장 3종 실험
4. 통과 후보 5개만 Editor 검토
5. 내부 초안 3개 생성 후 아직 발행하지 않고 읽기 경험 평가

이 순서는 지금 가능한 것과 앞으로 필요한 것을 연결한다. 핵심은 Telegram 발행을 서두르지 않고, 먼저 **후보가 생기는가, 읽고 싶은가, 선을 넘지 않는가**를 검증하는 것이다.
