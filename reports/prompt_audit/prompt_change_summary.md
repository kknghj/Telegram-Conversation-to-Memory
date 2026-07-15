# Prompt Change Summary

- 날짜: 2026-07-15
- 목적: Phase 2 reflection agent 기준으로 질문·해석 규칙의 중복/충돌을 줄이고, 모델 비교 실험의 고정 프롬프트 버전을 만든다.

## Prompt hashes

| Prompt | Before (audit start) | After cleanup |
|--------|----------------------|---------------|
| `memory_archive_system_prompt.txt` | `00cb6f1c43b78b9eb2423ef4f4b96ff293f83ecebb4330548f58a4abf3fd08fd` | `7ee1690910065a4cbffb2046da6fea7e089558deb6e01195abbcec2e6a607414` |
| `question_generation_prompt.txt` | `7b0aae7c7bab3dbf69ef677b5ec0c77850c0bf64d39ae7b12bd3024fe914edfd` | `6a124533dc79bb9399e503b509380aca47f467db1b0a5ce10f97b039cd1df3d1` |

## Canonical sources (정리 후)

1. 질문: `docs/question_strategy.md`
2. 해석/원칙: `docs/MEMORY_ARCHIVE_PRINCIPLES.md`
3. 초안 추출 정책: `docs/PROMPT_POLICY.md` (질문 확장은 question_strategy로 위임)
4. runtime: `memory_archive_system_prompt.txt`, `question_generation_prompt.txt`
5. 집행: `fidelity.py`, `question.py`, `question_quality.py`

## Changes made

### Runtime prompts

- archive 프롬프트: 질문 생성 역할 제거, meaning_check→followup 지침 삭제
- archive 프롬프트: `Rule 1`/`Rule 4` → `EditChecklist`/`ConsistencyCheck`로 라벨 변경 (failure Rule 번호와 분리)
- question 프롬프트: 한 번에 1개 질문 vs 세션 상한 2회 구분 명시, Rule 5 라벨을 의미 이름으로 완화

### Docs

- `PROMPT_POLICY.md`: question_strategy 위임 배너, stale max-1/정확도-only를 레거시로 표시
- `MEMORY_ARCHIVE_PRINCIPLES.md` §4: 한 번에 1개 / 세션 max 2 / gate
- `user_conversation_profile.md` §5.2: 현재 운영 max 2, 2–4는 장기 희망
- `question_strategy.md` §8: Rule 7 및 네임스페이스 표 추가

### Intentionally kept duplicates

- 성장 서사 금지: prompt + fidelity
- meaning_check 제한: question prompt + Python
- positive reframe 금지: question prompt + Python

### Not changed (out of scope / high risk)

- `question_quality.py`의 음식/콩국수 휴리스틱 (incident 근거 유지)
- failure Rule 4 umbrella 세분화
- 레거시 `REFLECTION_AGENT_ENABLED=false` 경로의 max-1 동작 (호환 유지)

## Risk

- archive 프롬프트에서 질문 지침을 제거해도 코드가 reflection agent ON일 때 `needs_followup`을 비우므로 운영 동작은 동일해야 한다.
- 문서 supersession이 incomplete하면 미래 기여자가 stale max-1을 다시 넣을 수 있다 → audit 보고서와 question_strategy 배너로 완화.
