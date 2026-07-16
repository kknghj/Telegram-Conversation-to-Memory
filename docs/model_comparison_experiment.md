# Model Comparison Experiment

평가 전용 실험이다. Supabase `drafts`는 읽기만 하고, production memory·Telegram·active draft는 변경하지 않는다.

운영 기본 모델은 2026-07-16 사람 블라인드 평가 이후 `gpt-5.6-luna`다 (근거: `docs/archive/incidents/model_selection_gpt56_luna_2026-07-16.md`). 비교 runner는 여전히 `OPENAI_MODEL`을 바꾸지 않고, `--models`로 받은 모델 ID를 함수 인자로 각 API 요청에 전달한다.

## Canonical rules for this experiment

- 질문 정책: `docs/question_strategy.md`
- 해석 원칙: `docs/MEMORY_ARCHIVE_PRINCIPLES.md`
- Prompt audit: `reports/prompt_audit/`
- Prompt hashes: `conversation_to_memory.evaluation.prompt_hash.get_prompt_hashes()`

질문 수 구분:

```text
한 번에 사용자에게 보내는 질문 수: 1개
세션 전체 질문 상한: 최대 2회
두 번째 질문: 게이트 통과 시에만 허용
```

이 실험은 **초안 + 첫 후속 질문 판단**만 비교한다 (Telegram으로 보내거나 대화를 이어가지 않음).

## PowerShell 실행 순서

```powershell
# 1. Supabase 사례 추출
python -m scripts.export_model_comparison_cases `
  --limit 30 `
  --seed 20260715

# 2. 세 모델 실행
python -m scripts.run_model_comparison `
  --dataset data/evaluation/model_comparison/<dataset_id>/cases.jsonl `
  --models gpt-4o-mini gpt-5.6-luna gpt-5.6-terra `
  --concurrency 1

# 3. 비교 화면 열기
python -m scripts.open_model_comparison_report `
  --run <run_id>

# 4. 내보낸 사용자 평가 요약
python -m scripts.summarize_model_reviews `
  --results reports/model_comparison/<run_id>/results.jsonl `
  --reviews <review.json>
```

## 출력 경로

```text
data/evaluation/model_comparison/<dataset_id>/cases.jsonl   # gitignored
data/evaluation/model_comparison/<dataset_id>/manifest.json
reports/model_comparison/<run_id>/comparison.html
reports/model_comparison/<run_id>/results.jsonl
reports/model_comparison/<run_id>/summary.json
reports/model_comparison/<run_id>/summary.csv
reports/model_comparison/<run_id>/run_manifest.json
```

## Resume / 재실행

- 완료된 `case × model`은 `checkpoints/`에 저장되며 resume 시 재호출하지 않는다.
- `--force`로 전부 재실행
- `--cases case_001` / `--only-models gpt-5.6-luna`로 부분 재실행
- 모델 실패 시 다른 모델로 fallback하지 않는다. `model_access_error`로 기록한다.

## 가격

`config/model_pricing.json` (검증일·출처 포함). 가격을 모르는 모델은 `estimated_cost_usd=null`.

## 테스트

```powershell
pytest -q
pytest -q -m model_comparison_live
```
