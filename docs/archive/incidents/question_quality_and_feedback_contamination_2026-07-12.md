# Question Quality and Feedback Contamination - 2026-07-12

> 상태: `conditional_pass` — 코드·회귀 테스트·두 실제 대화 fixture replay 통과. live 신규 기억 관찰은 미검증. 기준일: 2026-07-12.
>
> 관련 역사 기록: `followup_question_recovery_2026-07-09.md` (질문률 0% 회귀). 본 문서는 그 후속 품질 사고를 다루며, 2026-07-09 문서를 덮어쓰지 않는다.

## 1. 배경

2026-07-09에 질문률 0% 회귀를 복구할 때 `accurate_summary != no_question_needed` 원칙을 세웠다. 이후 질문은 다시 나오기 시작했지만, 실제 live 기록에서 **이미 답한 내용을 재질문**하거나 **주변 예시를 핵심처럼 확대**하는 품질 실패가 관찰되었다.

이번 사고의 핵심은 질문 수가 아니라 질문 판단의 축이 여전히 섞여 있었다는 점이다.

```text
accurate_summary != no_question_needed
archive_gap != reflective_handle
followup_answer != meta_feedback
```

## 2. 실제 사용자 영향

1. 도스토옙스키 일화와 현재 상황의 연결을 원문에서 이미 설명했는데, 봇이 같은 연결을 다시 물었다. 사용자는 같은 내용을 반복 답변해야 했고, 이어진 비교 질문까지 부담이 커졌다.
2. 여름 메뉴 추천앱 기록에서 마감·제품 기준·프로젝트 성격이 핵심이었는데, 봇이 `콩국수`를 중심으로 질문을 이어갔다. 서로 다른 추상화 수준을 비교했고, 사용자의 질문 오류 피드백이 기억 원문에 섞였다. `GPT`가 `people`에 들어갔다.

## 3. 재현 대화

### 사례 A — 이미 답한 연결 재질문

사용자 원문 요약:

- 주술회전 가챠에 38만 원 사용, 중복 캐릭터로 낭비 감각
- 돈이 부족할 때마다 인기 작품을 썼다는 도스토옙스키 일화를 떠올림
- 낭비 복구를 위해 토스 미니앱 공모전 참여를 생각함

봇 질문:

- `도스토옙스키의 일화와 관련해, 그의 이야기가 현재 상황에 어떤 식으로 연결된다고 느끼나요?`
- 이후 유사 비교 질문 추가

### 사례 B — 낮은 중요도 앵커 + 메타 피드백 오염

사용자 원문 요약:

- GPT와 아이디어 회의 후 토스 미니앱 공모전에 여름 메뉴 추천앱 제출 결정
- 제품 기준, 마감(7/29), 단기 프로젝트 성격, 상금 vs 완성 우선순위

봇 질문:

- `어떤 특정한 음식이나 가게를 떠올렸나요?`
- 답변의 `콩국수`를 받아 `콩국수 vs 감정 기반 추천` 비교

사용자 피드백:

- `맥락에 맞지 않은 질문이야. 둘 중 무엇이 낫냐고 물으려면 같은 격이어야 해.`

## 4. 실패 유형

| 유형 | 설명 |
|------|------|
| `redundant_question` / `answered_already` | 원문에 이미 있는 연결·설명을 다시 물음 |
| `low_salience_anchor` | 핵심 테마보다 주변 예시(콩국수)를 질문 중심으로 확대 |
| `category_mismatch` | 음식 인스턴스와 추천 전략처럼 추상화 수준이 다른 비교 |
| `meta_feedback_leaked_into_memory` | 질문 품질 피드백이 기억 원문·요약에 유입 |
| people 오분류 | `GPT` 등 비인간 엔티티가 `people`에 저장됨 |

실패 스냅샷:

- `telegram_20260712_dostoevsky_redundant_question`
- `telegram_20260712_summer_menu_low_salience_anchor`

경로: `data/evaluation/interpretation_failures.jsonl`

## 5. 과거 질문률 0% 사고와의 관계

2026-07-09 사고는 `information_already_complete`가 meaning_check 억제를 넘어 association/contrast까지 죽인 것이 문제였다.

이번 사고는 그 반대 극단이다.

- 질문을 복구한 뒤, **원문에 이미 답이 있는지**와 **앵커 중요도/추상화 수준**을 충분히 검증하지 않았다.
- reflective handle이 있다는 이유로 중복·저품질 질문까지 허용될 수 있었다.
- 후속 입력을 분류하지 않아 메타 피드백이 기억 재료로 섞였다.

잘못된 해결책은 다음과 같다.

- 정확한 기억에는 질문하지 않기 → 2026-07-09 회귀 재발
- 질문 수를 1회로 강제하기 → 새 정보가 생긴 뒤의 정당한 두 번째 질문까지 막음

## 6. 잘못된 해결책 (명시적 거부)

1. **정확한 기억에는 질문하지 않기**  
   `archive_gap=none`은 meaning_check 불필요를 뜻하지, 확장 질문 금지를 뜻하지 않는다.
2. **질문 수를 1회로 강제하기**  
   `REFLECTION_MAX_QUESTIONS=2`를 유지한다. 2회는 목표가 아니라 상한이며, 두 번째 질문은 게이트를 통과할 때만 허용한다.
3. **질문률을 코드로 강제하기**  
   최근 N건 질문률은 관측 지표일 뿐이다. 낮다고 부적절한 질문을 만들지 않는다.

## 7. 핵심 설계 결정

1. **archive_gap과 reflective_handle 분리**  
   정확도 부족과 회고 확장 가능성을 독립 계산한다.
2. **질문 후보 생성과 검증 분리**  
   후보 1~3개를 만든 뒤 `answered_already`, `low_salience_anchor`, `category_mismatch` 등으로 걸러 가장 좋은 것만 보낸다.
3. **최대 2회 유지 + 두 번째 질문 게이트**  
   첫 응답이 `followup_answer`이고 새 정보가 추가되며, 새 unresolved/strong handle이 있을 때만 2회째 허용.
4. **후속 응답 분류**  
   `followup_answer`만 기억 원문에 포함한다. `pass` / `question_rejection` / `meta_feedback`는 원문 제외 후 REVIEW.
5. **엔티티 역할 분리**  
   `people` / `projects` / `tools` / `events`를 후처리한다. 공모전을 전역적으로 특정 앱에 매핑하지 않는다.

## 8. 수정 파일

- `conversation_to_memory/bot/followup_response.py` (신규)
- `conversation_to_memory/memory/question_quality.py` (신규)
- `conversation_to_memory/memory/question.py`
- `conversation_to_memory/bot/chat_service.py`
- `conversation_to_memory/bot/question_flow.py`
- `conversation_to_memory/bot/session.py`
- `conversation_to_memory/bot/failure_hooks.py`
- `conversation_to_memory/failure_recorder.py`
- `conversation_to_memory/memory/fidelity.py`
- `conversation_to_memory/memory/service.py`
- `conversation_to_memory/prompts/question_generation_prompt.txt`
- `tests/test_question_quality_regression.py`
- `tests/test_question_quality_replay.py`
- `docs/question_strategy.md`
- `docs/future_roadmap.md`
- `docs/validation_plan.md`

## 9. 회귀 테스트

- 이미 답한 도스토옙스키 연결 재질문 차단
- strong handle이어도 `already_answered` 후보 탈락
- `archive_gap=none`만으로 전체 skip 금지
- 낮은 중요도 앵커·추상화 불일치 비교 차단
- 후속 응답 분류 및 메타 피드백 원문 제외
- 두 번째 질문 게이트 / 최대 2회
- GPT→tools, 여름 메뉴 추천앱→projects, 토스 미니앱 공모전→events
- 공모전→여름 메뉴 앱 전역 매핑 금지
- 두 실제 대화 fixture replay

검증 명령: `python -m pytest -q` → 287 passed (2026-07-12)

## 10. 검증 결과

| 항목 | 결과 |
|------|------|
| 단위/회귀 테스트 | passed |
| 두 실제 대화 fixture replay | passed |
| interpretation failure 2건 기록 | passed |
| live 신규 기억 관찰 | not_started |

## 11. 남은 위험

- LLM이 후보 스키마를 약하게 채우면 코드 휴리스틱에 더 의존한다.
- `answered_already` 탐지가 고유명사·연결 표현 휴리스틱 중심이라, 다른 형태의 중복 질문은 일부 놓칠 수 있다.
- live에서 두 번째 질문 게이트가 과도하게 보수적이면 질문률이 다시 낮아질 수 있다. 강제 생성으로 보정하지 말고 게이트 사유를 관측한다.
- 엔티티 앱 이름 추출은 `제출/개발/만들` 등 동사 패턴에 의존한다.

## 12. 상태

`conditional_pass` — 구현과 자동 검증은 완료. 다음 live 20건 관찰 후 `passed` 또는 추가 수정 여부를 결정한다.
