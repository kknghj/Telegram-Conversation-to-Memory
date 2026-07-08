# Decision Trace 운영 확인용 SQL

Render 상시 운영 중 "왜 후속 질문이 안 나왔는가", "왜 project tag가 빠졌는가"를
Supabase `decision_traces` 테이블로 사후 분석하기 위한 쿼리 모음이다.

Supabase Dashboard > SQL Editor에서 실행한다.

## 테이블 개요

- 메모 저장(「저장」) 시점에 trace 1건이 확정 저장된다. `memory_id`는 memories 테이블의 row id.
- 요약 분석 자체가 실패한 경우(LLM 호출 실패·JSON 파싱 실패)는 `memory_id`가 null인 trace가 즉시 저장된다.
- `question_trace.reason` 주요 값:
  - `information_already_complete` — 질문이 필요 없다고 정상 판단
  - `max_questions_reached` — 질문 한도 도달 (LLM 미호출)
  - `summary_with_negative_emotion` / `fatigue_keyword_detected` / `positive_reframe_risk` / `multiple_questions_in_one` / `forbidden_inference_term` / `empty_question_generated` — 검증 규칙에 의한 생략
  - `generation_failed` + `error`(`json_parse_failed` | `llm_call_failed`) — 생성 시도했으나 실패
  - `analysis_failed` — 요약 분석 실패로 질문 로직 자체가 호출되지 않음 (`evaluated=false`)
- `project_trace.reason` 주요 값:
  - `no_project_signal_in_source` — 프로젝트 감지 실패 (원문·LLM 모두 후보 없음)
  - `candidate_without_selection` — 후보는 있었지만 선택 안 됨 (confidence 0)
  - `tag_save_failed` — 선택은 했지만 메모 저장 실패로 tag 미기록
  - `analysis_failed` — 분석 단계 실패
- `project_trace.confidence`: 원문 별칭 매칭(규칙 기반) 확인 시 1.0, LLM 추출만 있으면 0.6.

## 후속 질문이 생략된 이유 집계

```sql
SELECT
  question_trace->>'reason' AS reason,
  COUNT(*) AS count
FROM decision_traces
GROUP BY reason
ORDER BY count DESC;
```

## 질문이 필요했지만 생성 실패한 사례

```sql
SELECT *
FROM decision_traces
WHERE
  question_trace->>'need_followup' = 'true'
  AND question_trace->>'generated' = 'false'
ORDER BY created_at DESC;
```

생성 시도 자체가 실패한 사례(LLM 실패·JSON 파싱 실패):

```sql
SELECT
  created_at,
  memory_id,
  question_trace->>'error' AS error,
  raw_input_preview
FROM decision_traces
WHERE question_trace->>'error' IS NOT NULL
ORDER BY created_at DESC;
```

생성은 되었지만 사용자에게 전송되지 않은 사례:

```sql
SELECT *
FROM decision_traces
WHERE
  question_trace->>'generated' = 'true'
  AND question_trace->>'sent' = 'false'
ORDER BY created_at DESC;
```

## 프로젝트 태그 누락 사례

```sql
SELECT *
FROM decision_traces
WHERE
  project_trace->>'detected' = 'true'
  AND project_trace->>'tag_written' = 'false'
ORDER BY created_at DESC;
```

누락 사유별 집계:

```sql
SELECT
  project_trace->>'reason' AS reason,
  COUNT(*) AS count
FROM decision_traces
WHERE project_trace->>'tag_written' = 'false'
GROUP BY reason
ORDER BY count DESC;
```

## 최근 30개 trace 확인

```sql
SELECT
  created_at,
  memory_id,
  question_trace,
  project_trace
FROM decision_traces
ORDER BY created_at DESC
LIMIT 30;
```

## 분석 단계 실패 (메모 저장 자체가 안 된 케이스)

```sql
SELECT
  created_at,
  error,
  raw_input_preview
FROM decision_traces
WHERE memory_id IS NULL
ORDER BY created_at DESC;
```
