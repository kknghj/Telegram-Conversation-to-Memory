# Evaluation Log — Supabase Integration

회고 평가·MVP 스냅샷·질문 실패 로그를 Supabase **remote mirror**로 연결하는 방법이다.

## 저장소 역할

| 데이터 | Canonical source | Supabase 테이블 |
|--------|------------------|-----------------|
| 패턴 카드 사용자 평가 | `data/evaluation/reflection_evaluations.jsonl` | `reflection_evaluations` |
| MVP 라운드 스냅샷 | `data/evaluation/mvp_round*_*.json` | `mvp_evaluations` |
| AI 질문/해석 실패 | `data/evaluation/interpretation_failures.jsonl` | `interpretation_failures` |

JSONL/JSON이 원본이다. Supabase sync는 **best-effort mirror** — 실패해도 로컬 저장은 유지된다.

---

## 1. Supabase 프로젝트 준비

1. [Supabase Dashboard](https://supabase.com/dashboard)에서 프로젝트 생성
2. **Project Settings → API**에서 확인:
   - `Project URL` → `SUPABASE_URL`
   - `service_role` secret → `SUPABASE_SECRET_KEY` (브라우저·GitHub에 노출 금지)

---

## 2. 마이그레이션 적용

`supabase/migrations/` 순서대로 SQL Editor에 실행한다.

| 파일 | 테이블 |
|------|--------|
| `001_create_reflection_evaluations.sql` | `reflection_evaluations` |
| `002_create_mvp_evaluations.sql` | `mvp_evaluations` |
| `003_create_interpretation_failures.sql` | `interpretation_failures` (신규) |
| `004_extend_mvp_evaluations.sql` | `mvp_evaluations` 컬럼 확장 |
| `009_extend_interpretation_failure_types.sql` | `interpretation_failures.failure_type` CHECK 확장 (`value_hidden_by_event`, `correction_partial`) |
| `010_extend_interpretation_failure_types_question_quality.sql` | `interpretation_failures.failure_type` CHECK 확장 (`redundant_question`, `low_salience_anchor`, `category_mismatch`, `meta_feedback_leaked_into_memory`) |

### Dashboard에서 실행

1. Supabase → **SQL Editor** → New query
2. `001` → Run, `002` → Run, `003` → Run, `004` → Run (순서 유지)

### CLI 사용 (선택)

```powershell
supabase link --project-ref <your-project-ref>
supabase db push
```

---

## 3. 환경변수

`.env`:

```env
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_SECRET_KEY=eyJhbGciOi...
```

확인:

```powershell
python -c "from app.evaluation_supabase import is_supabase_configured; print(is_supabase_configured())"
```

`True`면 연동 준비 완료.

---

## 4. 테이블 구조 요약

### reflection_evaluations

패턴 카드 1장당 1행. upsert key: `(evaluation_id, card_id)`

| 컬럼 | 설명 |
|------|------|
| `accuracy` | `correct` \| `partial` \| `wrong` |
| `action` | `keep` \| `revise` \| `discard` |
| `raw` | 원본 JSONL 행 |

### mvp_evaluations

MVP 라운드 1회당 1행. upsert key: `evaluation_id`

| 컬럼 | 설명 |
|------|------|
| `final_judgment` | `fail` \| `not_ready` \| `partial_success` \| `conditional_success` \| `success` \| `strong_success` |
| `reflection_judgment` | 회고 가치 판정 (별도) |
| `question_quality_grade` | `excellent` \| `good` \| `fair` \| `poor` |
| `period_start`, `period_end` | 평가 기간 |
| `failure_count` | 평가 시점 interpretation_failures 건수 |
| `pattern_cards` | 패턴 카드 요약 JSON |
| `payload` | 전체 MVP JSON |

### interpretation_failures

질문/해석 실패 1건당 1행. upsert key: `failure_key` (`conversation_id|timestamp|failure_type`)

| 컬럼 | 설명 |
|------|------|
| `failure_type` | `repeated_question`, `korean_misparse`, `correction_ignored`, `correction_partial`, `memory_unavailable_ignored`, `inappropriate_positive_reframe`, `value_hidden_by_event` |
| `severity` | `low` \| `medium` \| `high` |
| `context` | 실패 직전 대화 (jsonb) |
| `fixed_rule` | Rule 1~7 |
| `prevented_by_rule` | Rule 적용 후 재발 여부 (선택) |
| `raw` | 원본 JSONL 행 |

> `correction_partial`, `value_hidden_by_event`를 쓰려면 `009_extend_interpretation_failure_types.sql`을 적용해야 한다.

---

## 5. 데이터 동기화

### 패턴 카드 평가 (reflection_evaluations)

```powershell
python scripts/sync_evaluations_to_supabase.py --path data/evaluation/reflection_evaluations.jsonl
```

또는 Python:

```python
from app.evaluation_supabase import sync_jsonl_to_supabase
sync_jsonl_to_supabase("data/evaluation/reflection_evaluations.jsonl")
```

### MVP 라운드 스냅샷 (mvp_evaluations + 관련 패턴 카드)

```powershell
# 3차 (기본값)
python scripts/sync_mvp_evaluations_to_supabase.py

# 2차
python scripts/sync_mvp_evaluations_to_supabase.py --path data/evaluation/mvp_round2_2026-06-19.json
```

### 한 번에 전체 동기화 (3차 MVP + 패턴 카드 + 질문 실패)

```powershell
python scripts/sync_all_evaluations_to_supabase.py
```

3차 MVP JSON: `data/evaluation/mvp_round3_2026-07-04.json`

### 질문/해석 실패 (interpretation_failures)

```powershell
python scripts/sync_interpretation_failures_to_supabase.py
```

출력 예:

```json
{
  "total": 4,
  "synced": 4,
  "failed": 0,
  "failed_items": []
}
```

---

## 6. 조회 예시

```python
from app.evaluation_supabase import load_evaluations_from_supabase
from app.mvp_evaluation_supabase import load_mvp_evaluations_from_supabase
from app.interpretation_failures_supabase import load_interpretation_failures_from_supabase

# 3차 패턴 카드 평가
cards = load_evaluations_from_supabase(evaluation_id="mvp_round3-2026-07-04")

# MVP 스냅샷
mvp = load_mvp_evaluations_from_supabase(evaluation_id="mvp_round3-2026-07-04")

# 질문 실패 유형별
failures = load_interpretation_failures_from_supabase(
    failure_type="inappropriate_positive_reframe"
)
```

Dashboard SQL:

```sql
-- 3차 패턴 카드 acceptance rate
SELECT accuracy, COUNT(*)
FROM reflection_evaluations
WHERE evaluation_id = 'mvp_round3-2026-07-04'
GROUP BY accuracy;

-- failure 유형 분포
SELECT failure_type, severity, COUNT(*)
FROM interpretation_failures
GROUP BY failure_type, severity;
```

---

## 7. 실패 시 복구

| 상황 | 조치 |
|------|------|
| sync 실패 | JSONL/JSON은 로컬에 있음 → 해당 sync 스크립트 재실행 (upsert idempotent) |
| CHECK constraint 오류 | migration 003/004 재확인, enum 값 소문자 확인 |
| RLS 차단 | service role key 사용 여부 확인 (anon key 아님) |

원칙: **항상 로컬 JSONL/JSON → Supabase 방향**으로만 동기화한다.

---

## 8. 관련 코드

| 파일 | 역할 |
|------|------|
| `app/evaluation_supabase.py` | reflection_evaluations |
| `app/mvp_evaluation_supabase.py` | mvp_evaluations |
| `app/interpretation_failures_supabase.py` | interpretation_failures |
| `scripts/sync_evaluations_to_supabase.py` | 패턴 카드 백필 |
| `scripts/sync_mvp_evaluations_to_supabase.py` | MVP 백필 |
| `scripts/sync_interpretation_failures_to_supabase.py` | 실패 로그 백필 |

---

## 9. MVP JSON 3차 예시 (선택)

`mvp_evaluations`에 3차를 올리려면 JSON에 확장 필드를 포함한다:

```json
{
  "evaluation_id": "mvp_round3-2026-07-04",
  "evaluation_type": "mvp_round",
  "round": 3,
  "evaluated_at": "2026-07-04",
  "memory_count": 88,
  "previous_memory_count": 50,
  "new_memory_count": 38,
  "period": { "start": "2026-06-09", "end": "2026-07-04" },
  "final_judgment": "partial_success",
  "reflection_judgment": "partial_success_to_success",
  "question_quality_grade": "fair",
  "failure_count": 4,
  "score": null,
  "user_validated": true,
  "pattern_cards": [
    { "card_id": "MVP3-PC-R3-01", "action": "keep" },
    { "card_id": "MVP3-PC-R3-02", "action": "discard" }
  ],
  "payload": {}
}
```

`payload`에는 전체 평가 리포트를 넣고, sync 시 `mvp_evaluation_to_supabase_row()`가 flat 컬럼으로 매핑한다.
