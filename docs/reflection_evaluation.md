# Reflection Evaluation — 안전장치 및 평가 로깅

1차 탐색적 회고 평가(21건·5일)에서 발견된 해석 위험을 막기 위한 **P0/P1 안전장치** 문서다.  
회고 기능 확장이 아니라, 근거·신뢰도·실패 기록의 **기반**을 만든다.

관련 코드:

- `conversation_to_memory/reflection/` — evidence tier, schema, cards, evaluation log
- `conversation_to_memory/prompts/reflection_card_safety_prompt.txt` — 회고 생성 시 안전 규칙
- `scripts/migrate_schema_version.py` — 기존 메모 schema_version 마이그레이션
- `data/evaluation/reflection_failures.jsonl` — 평가 failure log (생성 시)

---

## 1. 왜 primary evidence가 필요한가

회고 카드의 최종 근거는 **사용자가 직접 말한 원문**이어야 한다.  
`conversation` 필드의 `role: user` 발화만 **primary evidence**다.

derived 필드(`event_summary`, `memory_candidate`, `summary` 등)는 모델이 정리·재서술한 결과라, 원문에 없는 조언·성장 서사·감정 해석이 섞일 수 있다.  
1차 평가에서 구스키마 4건의 `memory_candidate`에 "지속적으로 노력하고 싶다", "감정을 잘 다스릴 방법을 찾아야겠다"처럼 **사용자 미발화 문장**이 확인되었다.

**규칙**

1. 회고 카드는 primary evidence 없이 생성하지 않는다.
2. derived evidence는 검색·후보 탐색에만 사용한다.
3. 최종 근거 인용에는 primary evidence가 반드시 포함되어야 한다.

---

## 2. 왜 memory_candidate를 최종 근거로 쓰면 위험한가

`memory_candidate`는 "다시 읽을 가치 있는 한 줄"을 목표로 하지만, 생성 단계에서:

- 원문에 없는 미래 의지("~하고 싶다")
- 조언형 마무리("~해야겠다")
- 성장 서사

가 추가될 수 있다. 회고 에이전트가 이를 근거로 삼으면 **INTERPRETATION_FAILURE**가 증폭된다.

**안전한 사용 순서**

1. `conversation` 원문에서 인용 (primary)
2. 필요 시 `event_summary`로 맥락 확인 (derived, 인용 보조)
3. `memory_candidate`는 카드 **초안 탐색**에만 사용, 최종 인용 금지

---

## 3. schema_version 기준

| 버전 | 조건 | 신뢰도 |
|------|------|--------|
| **1** (legacy) | `summary`/`emotion` 중심, `event_summary`/`user_emotions` 없음 | 자동 낮춤 + `legacy_schema` 경고 |
| **2** (current) | `event_summary`/`user_emotions`/`interpretation_risk` 포함 | 기본 |

- 새로 저장되는 메모: `schema_version: 2` ( `LocalJsonStorage` )
- 기존 파일: `scripts/migrate_schema_version.py` — **백업 후** `schema_version` 필드 추가

```bash
.venv\Scripts\python.exe scripts/migrate_schema_version.py
.venv\Scripts\python.exe scripts/migrate_schema_version.py --dry-run
```

---

## 4. Failure Taxonomy 정의

| 유형 | 의미 |
|------|------|
| `SEARCH_FAILURE` | 관련 기록을 찾지 못함 |
| `CONNECTION_FAILURE` | 관련 기록은 있으나 연결 이유가 피상적 |
| `INTERPRETATION_FAILURE` | 근거보다 의미를 크게 확대 |
| `OBVIOUS_INSIGHT` | 맞지만 너무 뻔함 |
| `OVER_GENERALIZATION` | 적은 사례를 성향으로 일반화 |
| `DATA_INSUFFICIENT` | 현재 데이터로 판단 불가 |
| `DUPLICATED_CARD` | 비슷한 카드 중복 |

**저장 위치:** `data/evaluation/reflection_failures.jsonl` (JSONL)

**스키마 예시:**

```json
{
  "report_id": "reflection-2026-06-13",
  "card_id": "connection-03",
  "card_type": "surprising_connection",
  "source_memory_ids": ["2026-06-09_230254", "2026-06-10_205011"],
  "sample_size": 2,
  "evidence_tiers_used": ["primary", "derived"],
  "schema_versions_used": [1, 2],
  "model_confidence": "medium",
  "failure_types": null,
  "failure_type": null,
  "failure_notes": null,
  "created_at": "..."
}
```

- 평가 전: `failure_types: null` 허용
- 평가 후: `EvaluationLogStore.update_failure_types()` 로 갱신
- **한 카드에 여러 failure_type 허용** (`failure_types` 배열). 호환용 `failure_type`은 첫 항목.

---

## 5. sample_size 표시 규칙

- `sample_size` = `source_memory_ids` 개수
- 사용자-facing 문장: `현재 기록(n=N)에서는 …`
- `sample_size < 3`: 신뢰도 기본 **low** 또는 **low~medium**
- `sample_size = 1`: **패턴·연결 카드 금지** → `single_observation` / `open_question`만
- 반복 패턴·연결 카드: **primary evidence 최소 2개**

검증 API: `validate_reflection_card(card, memories_by_id)`

---

## 6. 현재 단계: 탐색적 평가

약 20~50건 메모 단계는 **최종 성능 평가가 아니다.**

목표:

- 적은 데이터에서 **어디까지 회고가 가능한지** 탐색
- **무엇을 절대 하면 안 되는지** (성격 일반화, derived-only 인용) 기록
- failure log로 30~50건 이후 **품질 비교** 가능하게 함

성공 기준은 정확도가 아니라, **실패 유형을 많이 발견·분류**하는 것이다.

---

## Evidence Tier 참조

```json
{
  "evidence_tier": "primary",
  "source_field": "conversation",
  "memory_id": "2026-06-10_205011",
  "quote": "너무 긴장되서 정말 하고 싶지 않아."
}
```

```json
{
  "evidence_tier": "derived",
  "source_field": "memory_candidate",
  "memory_id": "2026-06-09_223830"
}
```

---

## API 요약

```python
from conversation_to_memory.reflection import (
    validate_reflection_card,
    EvaluationLogStore,
    EvaluationLogEntry,
    detect_schema_version,
    evidence_tier_for_field,
)
```
