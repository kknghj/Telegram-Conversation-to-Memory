# open_questions 오염 · 수정 부수효과 · dict join 오류 — 2026-07-17

> 상태: `conditional_pass` — 코드·단위 테스트 통과. luna live 재관찰 전. 기준일: 2026-07-17.
>
> 관련: `question_quality_and_feedback_contamination_2026-07-12.md` (메타 피드백 원문 유입). 본 문서는 씨앗 필드·수정 UX 사고를 다루며 이전 문서를 덮어쓰지 않는다.

## 1. 배경

Phase 2 luna live 관찰 중 `open_questions` 채움과 검토 단계 수정 UX에서 품질 실패가 연속 관찰되었다. 동시에 LLM이 문자열 목록 필드에 dict를 넣어 Telegram 검토 메시지가 `str.join`에서 깨지는 오류도 확인되었다.

제품 정의상 `open_questions`는 **사용자가 스스로 던진 미해결 질문의 원문 인용**이다. AI가 만들고 싶은 다음 회고 질문이나 시스템 상호작용 문장이 들어가서는 안 된다. 수정은 요청한 항목만 바꾸고 승인 대기 중인 나머지 초안을 보존해야 한다.

## 2. 실제 사용자 영향

### 사례 A — 탁구장 (발명형 open_question)

- 원문에 있는 궁금증(“왜 … 탁구대를 새로 들이고 … 궁금해”)은 적절했다.
- 원문에 없는 `"이용할 수 있다면 어떤 방식으로 탁구를 치고 싶은지"`가 `open_questions`에 추가되었다.
- 후속에서 사용자는 불만 초점이 “이용 불가”이며 남들 운영은 상관없다고 닫았는데, 씨앗 필드는 운영/가정형 탐색을 열린 질문처럼 남겼다.

### 사례 B — 엄마 피부 감촉 (메타 오염 + 수정 과삭제 + 부수 재작성)

1. 분석/표시 중 `오류: sequence item 0: expected str instance, dict found`가 노출되었다.
2. 사용자가 `무슨일이야`라고 묻자, 그 문장이 `open_questions`와 `key_phrases`에 들어갔다.
3. `수정 open questions에 무슨일이야는 삭제해줘`를 요청했는데:
   - 요청한 항목뿐 아니라 **유효한 슬픔/죄책감 미확정 질문까지** `open_questions`가 `[]`로 비었다.
   - topic, event_summary, emotions, people, tags, memory_type 등 **요청하지 않은 필드가 함께 재작성**되었다.

## 3. 실패 유형

| 유형 | 설명 |
|------|------|
| `open_questions_invented` | 원문에 없는 가정형·확장형 질문을 씨앗 필드로 저장 |
| `open_questions_meta_leak` | 오류 반응·상태 확인(`무슨일이야`)이 씨앗 필드로 유입 |
| `edit_full_regenerate_drift` | 좁은 수정 요청인데 초안 전체를 LLM이 다시 씀 |
| `edit_over_deletion` | 항목 하나만 지우라는 요청에 배열 전체를 비움 |
| `list_field_dict_join` | 문자열 목록 필드에 dict가 들어가 `join` 실패 |

## 4. 원인

1. **규칙이 프롬프트에만 있음** — `open_questions` 원문 인용 규칙(`FL-002`)이 코드로 강제되지 않았다.
2. **질문 LLM 스키마에 필드만 있고 정의 없음** — `merge_question_into_draft`가 질문 LLM의 `open_questions`를 초안에 합칠 수 있었다.
3. **수정 = 전체 재생성** — `previous_draft`를 패치/검증에만 쓰고 LLM 입력의 수정 기준으로 넘기지 않았다. 결정론 패치는 `value_tags`·시제·유형 등에 한정되어 `open_questions` 항목 삭제·비대상 필드 보존이 없었다.
4. **메타 분류 공백** — `무슨일이야`류가 followup `meta_feedback`으로 잡히지 않거나, recording 경로에서 원문에 섞인 뒤 씨앗 필드로 승격되었다.
5. **dict 목록** — LLM이 `unsupported_inferences` 등에 dict를 넣으면 표시 경로의 `join`이 깨졌다. (`coerce_text_list`로 당일 1차 방어)

## 5. 대처 (구현)

| 조치 | 내용 |
|------|------|
| 원문 가드 | `filter_grounded_open_questions` — 원문 substring이 아닌 항목·메타 문장 제거 (`validate_draft`) |
| 메타 키프레이즈 | `filter_meta_key_phrases` — `무슨일이야` 등을 `key_phrases`에서 제거 |
| 질문 병합 차단 | `merge_question_into_draft`가 `open_questions`를 더 이상 합치지 않음 |
| 수정 안정화 | 기존 초안을 LLM에 전달 + `stabilize_edit_against_previous`로 좁은 수정 시 비대상 필드 복원 |
| 항목 삭제 패치 | `parse_open_question_removals` / `apply_edit_patches`로 요청된 open_question만 삭제 |
| 메타 분류 | followup `META_FEEDBACK_PHRASES`에 `무슨일이야` 등 추가 |
| 프롬프트 | archive: 메타/발명 제외·수정 시 비대상 유지; question: `open_questions`는 빈 배열 유지 |
| dict join | 기존 `coerce_text_list` 유지 (표시·정규화) |

주요 코드:

- `conversation_to_memory/memory/fidelity.py`
- `conversation_to_memory/memory/service.py`
- `conversation_to_memory/memory/question.py`
- `conversation_to_memory/bot/followup_response.py`
- `conversation_to_memory/prompts/memory_archive_system_prompt.txt`
- `conversation_to_memory/prompts/question_generation_prompt.txt`

테스트:

- `tests/test_fidelity.py` — 발명/메타 필터, open_question 단독 삭제 시 타 필드 보존
- `tests/test_question_generation.py` — 질문 LLM open_questions 비가드 병합
- `tests/test_question_quality_regression.py` — `무슨일이야` → `meta_feedback`

## 6. 아직 남은 것

- luna live에서 동일 패턴(발명·메타·좁은 수정) 재발 여부 관찰
- recording 상태에서 오류 직후 메타 문장을 `user_texts` 자체에서 제외하는지는 아직 선택적(씨앗 필드 가드가 1차 방어)
- 과거 승인 기억의 `open_questions` 일괄 재정리는 하지 않음 (로드맵 원칙)

## 7. 판정

- 구현·단위 테스트: 통과 → 사고 대응 `conditional_pass`
- Phase 2 전체: luna live 종결 관찰 전까지 `conditional_pass` 유지
