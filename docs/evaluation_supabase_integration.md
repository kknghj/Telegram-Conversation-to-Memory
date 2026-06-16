# Evaluation Log — Supabase Integration

회고 카드 **사용자 평가 observation log**를 Supabase에 remote mirror로 연결하는 방법이다.

## 왜 JSONL을 canonical source로 유지하는가

평가 로그는 학습 데이터가 아니라 **관찰 가능한 사실**의 기록이다.

| 역할 | 저장소 |
|------|--------|
| **Canonical source** | `data/evaluation/reflection_failures.jsonl` |
| **Remote mirror / query layer** | Supabase `reflection_evaluations` |

JSONL을 원본으로 두는 이유:

1. **오프라인·로컬 우선** — Telegram 봇과 평가 스크립트는 네트워크 없이도 동작해야 한다.
2. **단순 복구** — 파일 하나를 백업·diff·gitignore 정책으로 관리하기 쉽다.
3. **Supabase 장애 격리** — mirror sync 실패가 평가 저장 자체를 막지 않는다.
4. **자동 학습 금지** — 현재 단계에서는 observation log만 쌓고, Supabase는 조회·집계용이다.

Supabase sync는 **best-effort mirror**이다. JSONL append가 먼저 성공하면, Supabase 실패는 warning만 남긴다.

---

## Supabase 테이블 구조

마이그레이션: `supabase/migrations/001_create_reflection_evaluations.sql`

테이블: `reflection_evaluations`

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | uuid PK | `gen_random_uuid()` |
| `evaluation_id` | text | 평가 세션/배치 ID |
| `evaluated_at` | timestamptz | 사용자 평가 시각 |
| `memory_count` | integer | 평가 당시 메모리 건수 |
| `card_id` | text | 카드 ID |
| `card_type` | text | 카드 유형 |
| `accuracy` | text | `correct` \| `partial` \| `wrong` |
| `interesting` | boolean | 가치: 흥미 |
| `revisit` | boolean | 가치: 재방문 |
| `evidence` | text | `sufficient` \| `weak` \| `wrong` |
| `failure_type` | text null | failure taxonomy |
| `user_comment` | text null | 사용자 코멘트 |
| `action` | text | `keep` \| `revise` \| `discard` |
| `raw` | jsonb | 원본 `CardEvaluation` JSON |
| `created_at` | timestamptz | mirror 최초 insert |
| `updated_at` | timestamptz | mirror 마지막 upsert |

제약:

- `UNIQUE (evaluation_id, card_id)` — upsert conflict key
- CHECK constraints on `accuracy`, `evidence`, `action`, `failure_type`
- RLS enabled (service-role client only in this phase)

---

## 환경변수 설정

`.env` (`.env.example` 참고):

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SECRET_KEY=your_service_role_secret_key
```

주의:

- `SUPABASE_SECRET_KEY`는 **service role / secret key** — GitHub에 커밋하지 않는다.
- 브라우저·프론트엔드·Telegram 클라이언트에서 사용하지 않는다.
- 서버/스크립트 전용이다.

환경변수가 없으면:

- `append_card_evaluation()` — JSONL만 저장
- `sync_evaluation_to_supabase()` — `False` 반환
- `load_evaluations_from_supabase()` — `[]` 반환

---

## 마이그레이션 적용

Supabase CLI 또는 Dashboard SQL Editor에서 실행:

```bash
supabase db push
# 또는 Dashboard → SQL Editor → 001_create_reflection_evaluations.sql 붙여넣기
```

---

## 일반 사용 흐름

### 1. 평가 저장 (자동 mirror)

```python
from conversation_to_memory.reflection import append_card_evaluation

append_card_evaluation({...})
# 1) JSONL append
# 2) SUPABASE_* 설정 시 upsert 시도 (실패해도 JSONL 성공)
```

`sync_supabase=False`로 mirror만 건너뛸 수 있다.

### 2. 기존 JSONL 백필

```powershell
python scripts/sync_evaluations_to_supabase.py
```

옵션:

```powershell
python scripts/sync_evaluations_to_supabase.py --path data/evaluation/reflection_failures.jsonl
```

출력 예:

```json
{
  "total": 5,
  "synced": 5,
  "failed": 0,
  "failed_items": []
}
```

### 3. Supabase에서 조회

```python
from app.evaluation_supabase import load_evaluations_from_supabase

rows = load_evaluations_from_supabase(evaluation_id="eval-001")
```

---

## 실패 시 복구

| 상황 | 조치 |
|------|------|
| append 중 Supabase sync 실패 | JSONL은 이미 저장됨 → `scripts/sync_evaluations_to_supabase.py` 재실행 |
| 백필 일부 실패 (`failed_items`) | 실패 항목 확인 후 네트워크/키/스키마 점검 → 스크립트 재실행 (upsert idempotent) |
| Supabase 스키마 불일치 | migration 재적용, CHECK constraint 위반 row 확인 |
| JSONL 손상 | git/백업에서 복구 후 백필 |

복구 원칙: **항상 JSONL을 기준으로 Supabase를 다시 upsert**한다. Supabase → JSONL 역동기화는 현재 단계에서 하지 않는다.

---

## 관련 코드

| 파일 | 역할 |
|------|------|
| `conversation_to_memory/reflection/evaluation_models.py` | Pydantic 모델 |
| `conversation_to_memory/reflection/evaluation_storage.py` | JSONL append/load/aggregate + optional sync |
| `app/evaluation_supabase.py` | Supabase client, upsert, query |
| `scripts/sync_evaluations_to_supabase.py` | JSONL → Supabase 백필 |
| `tests/test_evaluation_supabase.py` | mock 기반 테스트 |

---

## 다음 단계

현재: **평가 observation log mirror**만 Supabase에 연결.

50건 이상 평가가 쌓인 뒤 다음을 판단한다:

- failure 분포·acceptance rate가 query layer에서 유용한가
- `memories` 전체를 Supabase에 mirror할 가치가 있는가
- RLS 정책·다중 사용자 확장이 필요한가

그 전까지는 **memories canonical source = 로컬 JSON** 정책을 유지한다.
