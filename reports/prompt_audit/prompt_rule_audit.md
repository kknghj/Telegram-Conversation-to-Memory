# Prompt Rule Audit

- 감사일: 2026-07-15
- 제품 맥락: Phase 2 회고 씨앗 수집 (`conditional_pass`). 기억 아카이브 MVP는 장기 콘텐츠 에이전트의 신뢰 기질이다.
- 현행 질문 정책: `docs/question_strategy.md` + reflection agent 경로
- 현행 해석/충실도: `docs/MEMORY_ARCHIVE_PRINCIPLES.md` + `fidelity.py`
- 상세 inventory: `prompt_rule_inventory.json`

## 규칙 우선순위 (정리 후)

1. 원문 충실도와 안전 hard rule  
2. 사용자 중단·피로·거부 신호  
3. 이미 답한 질문 및 중복 질문 차단  
4. 질문 후보의 근거성과 중요도  
5. 질문 유형 선택  
6. 표현 스타일과 다양성  

낮은 우선순위 규칙이 높은 우선순위를 무효화하면 안 된다.

## Canonical sources

| 영역 | Canonical |
|------|-----------|
| 질문 정책 | `docs/question_strategy.md` |
| 해석/아카이브 원칙 | `docs/MEMORY_ARCHIVE_PRINCIPLES.md` |
| 추출 프롬프트 정책 | `docs/PROMPT_POLICY.md` (질문 확장 정책은 question_strategy로 위임) |
| 사용자 취향 | `docs/user_conversation_profile.md` |
| runtime 초안 프롬프트 | `memory_archive_system_prompt.txt` |
| runtime 질문 프롬프트 | `question_generation_prompt.txt` |
| 집행 | `fidelity.py`, `question.py`, `question_quality.py` |

`docs/archive/`와 `prompts/legacy/`는 배경/증거만. 현행 규칙으로 쓰지 않는다.

## 확인된 충돌

### 1. 후속 질문의 목적

| 출처 | 주장 |
|------|------|
| `PROMPT_POLICY` / `MEMORY_ARCHIVE_PRINCIPLES` (구) | 정확도 확인용만 |
| `question_strategy` / `question_generation_prompt` (현행) | association, contrast, value_probe 등 확장 허용 |

**실제 동작 (REFLECTION_AGENT_ENABLED=true):** `question.py`가 확장 질문을 생성. 초안 모델의 `needs_followup`은 코드가 `false`로 고정.

**정리:** question_strategy를 질문 정책 canonical로 지정. PROMPT_POLICY/MEMORY 원칙은 레거시 경로 설명 + 위임 배너.

### 2. 질문 수

| 구분 | 값 |
|------|-----|
| 한 번에 사용자에게 보내는 질문 수 | **1개** |
| 세션 전체 질문 상한 | **최대 2회** (`REFLECTION_MAX_QUESTIONS`) |
| 두 번째 질문 | **게이트 통과 시에만** |

문서의 "최대 1개"는 레거시 Archivist 경로 또는 한 번에 보내는 개수와 혼동된 표현이다.

### 3. 해석과 질문 역할 분리

| 구성 | 역할 |
|------|------|
| `service.analyze_recording` | 기억 초안 |
| `question.generate_question` | 질문 후보 |
| 초안 JSON의 `needs_followup` | reflection agent ON이면 무시(항상 false) |

archive 프롬프트에 남아 있던 meaning_check→followup 지침은 역할 분리와 충돌하므로 제거.

## 규칙 표

| 규칙 | 중복 위치 | 충돌 위치 | 현재 실제 동작 | 정리 결정 | 변경 위험 | 관련 테스트 |
|------|-----------|-----------|----------------|-----------|-----------|-------------|
| I-001 성장서사 금지 | prompt, PROMPT_POLICY, MEMORY, fidelity | — | prompt+fidelity | keep | 낮음 | fidelity, interpretation_failures |
| I-005 가치관 우선 | prompt, fidelity, failure Rule 6 | — | heuristics 적용 | keep (S-006 merge) | 낮음 | test_interpretation_failures |
| F-002 수정 검증 | prompt "Rule 1", failure Rule 7 | Rule 번호 충돌 | edit loop | rewrite 라벨 | 낮음 | test_human_ideal_regression |
| Q-001 accurate≠no_question | question prompt, strategy, quality | Q-010 stale docs | decide_question_policy | keep | 낮음 | question_generation, quality_replay |
| Q-003 meaning_check 제한 | question prompt, strategy, code | Q-012 archive prompt | can_use_meaning_check | keep; Q-012 remove | 중간 | test_can_use_meaning_check_* |
| Q-004 확장 질문 유형 | strategy, quality | Q-010 | expansion modes | keep | 중간 | quality_replay |
| Q-006 세션 max 2 + gate | question prompt, strategy, code | Q-011/Q-013 docs | get_max_questions + gate | keep | 중간 | question_generation |
| Q-010 정확도만 | PROMPT_POLICY, MEMORY §4 | Q-001/Q-004 | 레거시 경로만 | archive | 낮음 | — |
| Q-011 max 0~1 | 구 문서, legacy context | Q-006 | 레거시 KEY_FOLLOWUP_ASKED | docs remove | 낮음 | — |
| Q-012 archive meaning_check | archive prompt | FL-001 | agent ON 시 무시 | remove | 중간 | role-separation tests |
| S-005 긍정 회상 금지 | question prompt, question.py | — | skip after summary | keep | 높음(보호) | test_question_safety_rules |
| FL-001 역할 분리 | service, question_flow | Q-012 | agent ON 경로 | keep + prompt cleanup | 중간 | memory_service, decision_trace |
| E-001 엔티티 분리 | strategy §7, fidelity | — | reclassify_entities | keep | 중간 | quality_replay |

## 의도적으로 유지한 중복

- **성장 서사 금지**: runtime prompt(모델 지침) + fidelity(집행). 한쪽에만 두면 누락 위험.
- **meaning_check 제한**: question prompt(의미 판단) + Python(결정적 차단).
- **S-005**: prompt 경고 + Python 차단. 사용자 보호 hard rule.

## 탐지 문제 요약

1. 동일 의미 반복: 성장 서사 금지, meaning_check (archive+question), max 1 vs max 2
2. 표현만 다른 동일 규칙: I-005 ↔ S-006, F-002 ↔ S-007
3. 동시 준수 불가: Q-010 vs Q-004, Q-011 vs Q-006
4. 문서만 있고 코드 없음: Q-010/Q-011 현행 반영 없음 (의도적으로 stale)
5. 코드만 있고 문서 약함: Q-009 fallback, FL-001 세부
6. 프롬프트 vs 후처리 기준 차이: archive meaning_check vs can_use_meaning_check
7. 과거 규칙 강제 테스트: 없음 확인 — safety/fidelity 테스트는 현행 보호와 일치
8. 도달 불가 규칙: archive followup when agent ON (코드가 무력화)
9. 과도한 구체 사례: question_quality의 음식/콩국수 휴리스틱 (incident 유래, 일반 규칙으로 과대 포장 위험 — 유지하되 incident에 근거)
10. 우선순위 모호: Rule N 다중 네임스페이스

## 관련 incident (배경만)

- `docs/archive/incidents/followup_question_recovery_2026-07-09.md` — superseded
- `docs/archive/incidents/question_quality_and_feedback_contamination_2026-07-12.md` — conditional_pass
