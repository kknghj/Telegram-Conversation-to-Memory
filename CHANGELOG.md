# Changelog

## [Unreleased]

### Fixed

- **value_tags 수정 무시**: 사용자가 `value_tags` 삭제를 요청해도 `validate_draft()`가 원문 키워드로 태그를 재주입하고, 수정 검증이 `value_tags`를 다루지 않아 반영되지 않던 문제를 수정했다.
- **「사용자 시간 절약」 맥락 오탐**: "시간을 낭비"처럼 개인 자기관리와 제품·절차 맥락에 모두 쓰이는 표현을 키워드만으로 태깅하던 문제를, 전체 문맥 판별(`is_user_time_saving_value`)로 보완했다.
- **수정 요청 일부 누락 (correction_partial)**: 사용자가 `reflection_value` 상향과 `temporal_status=current`를 동시에 요청해도 하나만 반영되던 문제를 수정했다. 출력 직전 체크리스트 검증(`verify_edit_requests`)과 결정론적 보정(`apply_edit_patches`), LLM 재시도를 추가했다.
- **temporal_status 오판**: `~하고 싶다` 등 현재 지향 원문이 `event_summary`의 `~라고 말했다` 요약 문체 때문에 `past`로 분류되던 문제를 수정했다. `infer_temporal_status()`가 사용자 원문만 기준으로 `current`를 판별한다.
- **reflection_value 과소 평가**: 인간상·가치관·장기 목표 등 회고 가치가 높은 발화가 `low`/`event`로 저장되던 문제를 `apply_reflection_value_heuristics()`로 보완했다.

### Added

- `fidelity.py`: `CURRENT_ORIENTED_MARKERS`, `HUMAN_IDEAL_MARKERS`, `naturalize_event_summary()`, `check_consistency()`, `enforce_consistency()`, `parse_edit_checklist()`, `verify_edit_requests()`, `apply_edit_patches()`
- `docs/question_strategy.md` Section 9–10: 메모 추출·수정 규칙 (Rule 7–12)
- `tests/test_human_ideal_regression.py`: 인간상/현재 지향 회귀 테스트
- `data/evaluation/interpretation_failures.jsonl`: telegram_20260706_human_ideal_temporal 실패 사례

### Changed

- `memory_archive_system_prompt.txt`: 원문 우선 시제 분류, event_summary 품질, 수정 검증·일관성 검사 규칙 반영
- `VALID_TEMPORAL_STATUS`에 `current` 추가
