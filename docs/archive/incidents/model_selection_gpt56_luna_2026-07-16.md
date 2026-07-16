# Operating Model Selection: gpt-5.6-luna — 2026-07-16

> 상태: `passed` — 30건×3모델 사람 블라인드 평가 완료 후 운영 모델을 `gpt-5.6-luna`로 확정. 기준일: 2026-07-16.
>
> 관련 문서: `docs/model_comparison_experiment.md`, `reports/model_comparison/run_20260715_seed/`, `docs/validation_plan.md` (2단계 회고 씨앗).
>
> 본 문서는 평가 도구 도입(2026-07-15) 이후의 **운영 모델 결정**을 기록한다. production drafts/memory는 평가 중에 변경하지 않았다.

## 1. 배경

Phase 2(회고 씨앗 수집)에서 요약·태깅·첫 후속 질문 품질이 운영 모델에 민감하다는 점이 확인되었다. 프롬프트 규칙을 정리한 뒤, 동일 사례·동일 규칙으로 세 모델을 공정 비교해 **어떤 모델을 Archivist(초안·태그)·질문 경로에 쓸지** 결정하기로 했다.

비교 대상:

| 모델 | 역할 후보 |
|------|-----------|
| `gpt-4o-mini` | 기존 운영 기본값 (저비용) |
| `gpt-5.6-luna` | GPT-5.6 계열 후보 |
| `gpt-5.6-terra` | GPT-5.6 계열 후보 |

실험은 평가 전용이다. Supabase `drafts`는 읽기만 했고, 비교 runner는 `OPENAI_MODEL`을 바꾸지 않은 채 `--models`로 요청별 모델을 지정했다.

## 2. 결정 과정

### 2.1 데이터셋·실행

- 데이터셋: `ds_20260715_seed` (seed=20260715, 30건; saved 29 / cancelled 1)
- 원본: Supabase `drafts` 읽기 전용 추출
- 실행: `reports/model_comparison/run_20260715_seed` — 90/90 성공 (초안 + 첫 질문)
- 블라인드 UI: `comparison.html` (모델 ID는 평가 후 reveal)
- 사람 평가 export: `review_run_20260715_seed.json`
- 요약: `human_review_summary.json` / `human_review_summary.md`

### 2.2 평가 축

초안(요약·해석·태깅)과 첫 후속 질문을 함께 보고, 사례마다 블라인드 라벨(A/B/C) 중 최선(`best`)과 점수를 남겼다.

| 축 | 의미 |
|----|------|
| fidelity | 원문 충실도 |
| interpretation | 해석 유용성 (과해석·코칭 없이) |
| question | 질문 유용성 |
| project_accuracy / over_interpretation / answered_again | 교차 품질 체크 |

### 2.3 사람 평가 결과 (30 reviews)

| model | wins | fidelity | interpretation | question | error_rate | avg_latency_ms | avg_cost/case |
|-------|-----:|---------:|---------------:|---------:|-----------:|---------------:|--------------:|
| gpt-4o-mini | 0 | — | — | — | 0.0 | 19513 | $0.001 |
| **gpt-5.6-luna** | **17** | **4.533** | **4.4** | **3.929** | **0.0** | **16134** | **$0.015** |
| gpt-5.6-terra | 5 | 4.433 | 4.067 | 3.393 | 0.0 | 16784 | $0.033 |

기타:

- tie: 8
- `project_accuracy_rate`: 1.0
- `over_interpretation_rate`: 0.0
- `answered_again_rate`: 0.0
- 세 모델 모두 `question_generation_rate` 0.9 / `question_reject_rate` 0.1 (자동 지표는 동등; 승부는 사람 점수)

### 2.4 판단 기준

1. **품질 우선**: win 수와 fidelity / interpretation / question 평균에서 luna가 전 축 1위.
2. **비용**: luna는 mini 대비 약 15×이지만 terra의 약 절반. 품질 격차(mini win 0, terra win 5 vs luna 17)를 고려하면 운영 가치 대비 수용 가능.
3. **지연**: luna가 세 모델 중 평균 응답이 가장 짧음.
4. **제품 원칙**: 원문 충실·과해석 억제가 사람 평가에서 깨지지 않음 (`over_interpretation_rate=0`).

## 3. 결론

**운영 기본 모델을 `gpt-5.6-luna`로 확정한다.**

적용 범위:

- 기억 초안 생성(요약·태그·구조화) — `OPENAI_MODEL` / `OPENAI_MEMORY_MODEL`
- 후속 질문 생성 — `OPENAI_MODEL` / `OPENAI_QUESTION_MODEL` (미설정 시 동일 fallback)

적용하지 않는 범위:

- 평가용 비교 runner의 `--models` 목록 (실험은 계속 다중 모델 가능)
- Reporter / Editor / 발행 경로의 별도 모델 선택 (아직 운영 기본과 분리되지 않았거나 미구현이면 추후 재검토)

## 4. 운영 전환 조치 (코드·설정)

저장소에서 기본값을 luna로 맞춘다.

| 위치 | 변경 |
|------|------|
| `render.yaml` | `OPENAI_MODEL=gpt-5.6-luna` |
| `.env.example` | 동일 |
| `conversation_to_memory/memory/service.py` | resolve 기본값 |
| `conversation_to_memory/memory/question.py` | resolve 기본값 |
| `conversation_to_memory/startup.py` | 배너 기본값 |
| `conversation_to_memory/debug_trace/recorder.py` | trace 기본값 |
| `docs/deployment_checklist.md`, `docs/architecture.md`, `README.md` | 문서 기본값 |

**Render Dashboard의 실제 `OPENAI_MODEL`은 Blueprint 동기화 또는 수동 env 변경 + 재배포가 필요하다.** 코드만 push해도 Dashboard에 예전 값이 남아 있으면 운영은 mini를 계속 쓸 수 있다.

## 5. 전환 후 관찰 (검증)

모델 결정은 끝났으나 Phase 2 live 관찰은 계속이다.

- [ ] Render 로그에 `OpenAI Model: gpt-5.6-luna` 확인
- [ ] live 신규 기억에서 중복 질문·메타 피드백 원문 유입·엔티티 오분류 관찰
- [ ] 비용·지연이 일 사용량에서 허용 범위인지 확인

## 6. 근거 경로

```text
docs/model_comparison_experiment.md
data/evaluation/model_comparison/ds_20260715_seed/manifest.json
reports/model_comparison/run_20260715_seed/run_manifest.json
reports/model_comparison/run_20260715_seed/results.jsonl
reports/model_comparison/run_20260715_seed/comparison.html
reports/model_comparison/run_20260715_seed/review_run_20260715_seed.json
reports/model_comparison/run_20260715_seed/human_review_summary.json
reports/model_comparison/run_20260715_seed/human_review_summary.md
```
