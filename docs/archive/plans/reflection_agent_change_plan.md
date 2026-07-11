# Reflection Agent — Change Plan

> 상태: `superseded` — 질문 생성 분리와 회고 씨앗 수집을 위한 과거 구현 계획입니다. 현행 제품 방향과 진행상태는 `../../future_roadmap.md`, 검증 기준은 `../../validation_plan.md`, 질문 정책은 `../../question_strategy.md`를 따릅니다. 격리일: 2026-07-11.

단순 요약봇에서 **회고형 대화 에이전트**로 발전시키기 위한 설계·변경 계획이다.  
이 문서는 **구현 전 설계**이며, 코드 변경은 이 계획 승인 후 단계적으로 진행한다.

관련 문서:

- `user_conversation_profile.md` — 사용자 대화 성향
- `question_strategy.md` — 질문 유형·제한 규칙
- `vision.md`, `PROMPT_POLICY.md` — 원문 충실 원칙 (유지·보완)

---

## 1. 현재 상태 요약

### 1.1 아키텍처

```text
사용자 메시지 (RECORDING)
  → 「요약」 트리거
  → analyze_recording()  [단일 OpenAI 호출]
       ├─ memory_archive_system_prompt.txt
       └─ 출력: draft JSON + needs_followup + followup_question
  → (선택) FOLLOWUP 1회
  → REVIEW → 저장 / 수정 / 취소
```

### 1.2 문제점

| 문제 | 영향 |
|------|------|
| 요약과 질문이 한 프롬프트에 혼재 | 질문이 `meaning_check`에 치우침 |
| 질문 1회 제한 | 연상형 대화 확장 불가 |
| 스키마가 “사건 아카이브” 중심 | 회고·패턴·열린 질문 축적 불가 |
| `recent_context`가 요약에만 사용 | memory_link 질문에 활용 안 됨 |

### 1.3 유지할 것

- Telegram 상태 머신 골격 (`RECORDING` → `FOLLOWUP` → `REVIEW`)
- `fidelity.py` 후처리
- 사용자 명시적 승인 (`저장` / `수정` / `취소`)
- SQLite 초안 + Local JSON 저장
- 성장 서사·교훈 금지

---

## 2. 목표 아키텍처

```text
사용자 메시지 (RECORDING)
  → 「요약」 또는 대화 확장 트리거
  → analyze_recording()     [요약 전용, 질문 생성 없음]
  → generate_question()       [질문 전용, 선택적 반복]
       ├─ analyze_utterance()   내부: topic/emotion/unresolved_point/...
       └─ question_generation_prompt.txt
  → validate_question()       [금지 패턴·meaning_check 제한]
  → FOLLOWUP (0~N회, MVP: 2~4회 상한)
  → finalize_draft()          [대화 전체 반영 최종 요약]
  → REVIEW → 저장
```

### 2.1 파이프라인 분리

| 단계 | 함수 (제안) | 프롬프트 | temperature |
|------|-------------|----------|-------------|
| 요약 | `analyze_recording()` | `memory_archive_system_prompt.txt` (개정) | 0.2 |
| 발화 분석 | `analyze_utterance()` | 동일 호출 내 system 또는 소형 프롬프트 | 0.2 |
| 질문 생성 | `generate_question()` | `question_generation_prompt.txt` (신규) | 0.4~0.5 |
| 질문 검증 | `validate_question()` | 코드 (fidelity 확장) | — |
| 최종 병합 | `finalize_draft()` | `analyze_recording()` 재호출 또는 patch | 0.2 |

**분리 이유**: 요약은 보수적으로, 질문은 연상·호기심을 위해 약간 높은 temperature. 역할 충돌 방지.

---

## 3. 질문 생성 로직 분리 (상세)

### 3.1 신규 모듈

```text
conversation_to_memory/memory/
  ├── service.py              # 기존 — 요약 중심으로 축소
  ├── question.py             # 신규 — 질문 생성 파이프라인
  ├── fidelity.py             # 확장 — validate_question()
  └── models.py               # (선택) UtteranceAnalysis, QuestionResult 타입
```

### 3.2 `analyze_utterance()` — 발화 분석

**입력**

- `user_texts`, `conversation`
- `current_draft` (요약 1차 결과)
- `recent_context`
- `question_session` (이전 질문 모드·횟수)

**출력**

```json
{
  "topic": "string",
  "emotion": {
    "labels": ["string"],
    "evidence_strength": "none | weak | medium | strong"
  },
  "unresolved_point": "string | null",
  "possible_memory_value": "low | medium | high",
  "key_phrases": ["string"],
  "emerging_themes": ["string"],
  "suggested_modes": ["association", "contrast"]
}
```

구현 옵션:

- **A안 (권장, MVP)**: `generate_question()` 단일 호출에서 분석+질문을 함께 반환. 호출 수 최소화.
- **B안 (성숙)**: `analyze_utterance()`를 별도 소형 호출로 분리. 질문만 재생성할 때 비용 절감.

MVP는 **A안**으로 시작하고, 인터페이스만 B안 분리가 가능하게 둔다.

### 3.3 `generate_question()` — 후속 질문 생성

**입력**: `analyze_utterance` 결과 + `question_session` + `user_conversation_profile` 요약 블록

**출력**

```json
{
  "question_mode": "association",
  "followup_question": "string",
  "needs_followup": true,
  "open_questions": ["string"],
  "reasoning": "string (internal)"
}
```

**프롬프트**: `conversation_to_memory/prompts/question_generation_prompt.txt`

- `user_conversation_profile.md`, `question_strategy.md` 핵심 규칙을 system에 포함
- `meaning_check` 제한 규칙 명시
- 금지 질문 목록 (`PROMPT_POLICY.md`와 동기화)

### 3.4 `validate_question()` — 코드 검증

`fidelity.py` 확장:

- 성장 서사·코칭 질문 패턴 탐지
- `meaning_check` 세션 제한 위반 시 fallback → `association`
- 빈 질문, 복합 질문(물음표 2개 이상) 거부
- 사용자 피로 키워드 시 `needs_followup: false`

### 3.5 `memory_archive_system_prompt.txt` 개정

**제거·비활성**

- `## 후속 질문` 섹션 전체
- JSON 스키마에서 `needs_followup`, `followup_question` (하위 호환 위해 optional 유지 가능)

**추가 (요약 단계)**

- `key_phrases`, `emerging_themes`, `open_questions` 추출 지침
- `memory_type`, `reflection_value` 판단 지침
- `model_interpretation` — “에이전트 해석”을 `memory_candidate`와 분리

### 3.6 핸들러 변경 (`handlers.py`)

| 현재 | 변경 |
|------|------|
| `analyze_recording()` 후 `_maybe_followup_or_review()` | `analyze_recording()` → `generate_question()` 루프 |
| `KEY_FOLLOWUP_ASKED` (bool) | `KEY_QUESTION_SESSION` (dict: count, modes, fatigue) |
| FOLLOWUP 1회 후 무조건 REVIEW | `max_questions` 또는 사용자 「그만」으로 종료 |
| `handle_followup`에서 재분석 | 매 턴 `generate_question()`; N회 후 `finalize_draft()` |

**새 사용자 명령 (MVP 후반)**

- `그만` / `넘어가` — 질문 루프 종료, REVIEW
- (선택) `요약` — 기록 중에도 1차 요약만 보기

### 3.7 하위 호환

- `normalize_draft()`가 unknown 필드 보존 (`extra` 또는 명시적 optional 필드)
- 기존 저장 JSON 읽기: 새 필드 없으면 default
- `needs_followup`/`followup_question` deprecated; 1버전 동안 병행 후 제거

---

## 4. 저장 JSON 스키마 확장

### 4.1 필드 정의

| 필드 | 타입 | 단계 | 설명 |
|------|------|------|------|
| `key_phrases` | `string[]` | draft + saved | 사용자 고유 표현·생생한 구절 (원문 인용) |
| `emerging_themes` | `string[]` | draft + saved | 대화에서 부상하는 주제 (복수 가능) |
| `open_questions` | `string[]` | draft + saved | 아직 닫히지 않은 질문·생각 |
| `related_past_patterns` | `object[]` | draft + saved | 과거 기록과의 연결 후보 (아래 구조) |
| `question_mode_used` | `string[]` | session meta → saved | 세션에서 사용한 질문 유형 목록 |
| `reflection_value` | `"low"\|"medium"\|"high"` | draft + saved | 회고 가치 추정 |
| `memory_type` | `string` or `string[]` | draft + saved | `event` \| `observation` \| `relation` \| `pattern` \| `reflection_seed` |
| `model_interpretation` | `string` | draft + saved | 에이전트 해석 (본문과 분리) |
| `user_confirmed` | `boolean` | saved only | 사용자가 「저장」으로 확정 시 `true` |

**`related_past_patterns` 요소 구조**

```json
{
  "source_memory_id": "2026-06-01_143022.json",
  "link_type": "keyword | person | project | emotion | theme",
  "overlap": "말이 안 통한다",
  "confidence": "low | medium",
  "user_acknowledged": false
}
```

- `confidence`는 에이전트 추정. `user_acknowledged`는 사용자가 연결을 인정했을 때만 `true`.

### 4.2 기존 필드와의 관계

| 기존 | 신규와 관계 |
|------|-------------|
| `topic` | `emerging_themes[0]`과 중복 가능; `topic`은 대표 1개 유지 |
| `memory_candidate` | 확정 본문; `model_interpretation`과 혼합 금지 |
| `tags` | `emerging_themes`에서 자동 제안 후 사용자 수정 가능 |
| `needs_followup` | deprecated → 질문 세션 메타로 이동 |
| `followup_question` | deprecated → `conversation`에 assistant 턴으로만 존재 |

### 4.3 `DEFAULT_DRAFT` 확장 (제안)

```python
DEFAULT_DRAFT = {
    # ... 기존 필드 ...
    "key_phrases": [],
    "emerging_themes": [],
    "open_questions": [],
    "related_past_patterns": [],
    "reflection_value": "medium",
    "memory_type": "event",
    "model_interpretation": "",
    # workflow only (saved 시 선택 포함)
    "question_mode_used": [],
}
# user_confirmed → 저장 시에만 True
```

### 4.4 REVIEW UI 변경 (제안)

`format_review_message()`에 섹션 추가:

- 🪶 핵심 표현 (`key_phrases`)
- 🌱 열린 질문 (`open_questions`)
- 🔗 과거 연결 후보 (`related_past_patterns`) — confidence low는 “참고” 표시
- ⚙️ 에이전트 해석 (`model_interpretation`) — “이 부분은 제 해석입니다” 라벨

`user_confirmed`는 저장 시 자동 `true`. 수정 시 `model_interpretation`만 고치는 경로 지원.

### 4.5 마이그레이션

- 기존 `data/memories/*.json`: 마이그레이션 스크립트 불필요 (읽을 때 default)
- SQLite `drafts.summary_json`: `normalize_draft()`가 새 필드 채움

---

## 5. MVP 범위 제안

### 5.1 Phase R0 — 문서·인터페이스만 (즉시, 코드 최소)

| 항목 | 내용 |
|------|------|
| 문서 | `user_conversation_profile.md`, `question_strategy.md`, 본 문서 |
| 코드 | 없음 또는 `models.py`에 TypedDict만 |
| 검증 | 설계 리뷰, 3~5개 시나리오 수동 walkthrough |

### 5.2 Phase R1 — 질문 분리 MVP (핵심)

**구현**

- [ ] `question_generation_prompt.txt` 추가
- [ ] `memory/question.py`: `generate_question()`, `validate_question()`
- [ ] `memory_archive_system_prompt.txt`에서 후속 질문 섹션 제거
- [ ] `handlers.py`: 질문 2~3회 루프, `KEY_QUESTION_SESSION`
- [ ] `meaning_check` 세션 1회 제한 (코드)
- [ ] `question_mode_used` 세션 추적

**스키마 (최소)**

- [ ] `key_phrases`, `emerging_themes`, `open_questions`
- [ ] `reflection_value`, `memory_type`
- [ ] `model_interpretation` (요약 프롬프트에서 분리 출력)

**의도적으로 제외**

- `related_past_patterns` 자동 생성 (recent_context 텍스트만 프롬프트에 넣는 수준)
- 기록 중 자유 질문 (여전히 `요약` 후 시작)
- `user_confirmed` 필드별 세분화 (저장 시 일괄 true 유지)

**성공 기준**

- 5회 연속 세션에서 meaning_check 연속 0건
- 질문 유형 2종 이상 번갈아 등장
- 저장 JSON에 새 필드 포함, 기존 테스트 통과

### 5.3 Phase R2 — 회고 품질 강화

**구현**

- [ ] `related_past_patterns` 구조화 + recent memories ID 매칭
- [ ] `finalize_draft()` — 질문 루프 후 전체 대화 재요약
- [ ] `archive_decision`, `memory_link` 질문 모드
- [ ] 질문 `그만` 명령
- [ ] `format_review_message()` 신규 필드 표시
- [ ] `tests/test_question_generation.py`

### 5.4 Phase R3 — 회고·검색 연계 (future_roadmap Phase 2+)

- 반복 `emerging_themes` 집계
- `open_questions` 재방문 큐
- 필터·주간 회고에서 `reflection_value`, `memory_type` 활용
- (선택) 사용자별 conversation profile 설정 파일

---

## 6. 점진적 도입 전략

### 6.1 기능 플래그 (제안)

`.env` 또는 설정:

```bash
REFLECTION_AGENT_ENABLED=false   # R1 완료 후 true
REFLECTION_MAX_QUESTIONS=3
REFLECTION_ALLOW_MEANING_CHECK=true
```

기존 동작: `REFLECTION_AGENT_ENABLED=false` → 현재와 동일 (질문 0~1, 기존 프롬프트).

### 6.2 롤아웃 순서

```text
1. 스키마 필드 추가 (normalize_draft, 저장 호환) — 동작 변화 없음
2. 질문 프롬프트 분리 + 플래그 off 상태로 테스트
3. 플래그 on, 개인 사용 1~2주
4. PROMPT_POLICY.md, mvp_scope.md, README 갱신
5. R2 기능 토글별 추가
```

### 6.3 리스크와 완화

| 리스크 | 완화 |
|--------|------|
| OpenAI 호출 증가 (질문마다 1회) | R1: 질문 상한 3; A안 단일 호출 |
| 질문이 코칭 톤으로 새는 경우 | `validate_question()` + 기존 fidelity |
| 스키마 비대화 | REVIEW preview는 핵심만; 전체 JSON은 저장 시 |
| 기존 테스트 깨짐 | 플래그 off 경로 유지; fixture 업데이트 |

---

## 7. 파일 변경 체크리스트

| 파일 | R1 | R2 |
|------|----|----|
| `docs/user_conversation_profile.md` | ✅ 작성 | 유지 |
| `docs/question_strategy.md` | ✅ 작성 | 유지 |
| `docs/archive/plans/reflection_agent_change_plan.md` | ✅ archive 보관 | 현행 지침으로 갱신하지 않음 |
| `prompts/question_generation_prompt.txt` | 신규 | 개정 |
| `prompts/memory_archive_system_prompt.txt` | 개정 | 개정 |
| `memory/question.py` | 신규 | 확장 |
| `memory/service.py` | 스키마·프롬프트 정리 | finalize |
| `memory/fidelity.py` | validate_question | 확장 |
| `bot/handlers.py` | 질문 루프 | 그만·finalize |
| `bot/session.py` | KEY_QUESTION_SESSION | 확장 |
| `tests/test_question_generation.py` | 신규 | 확장 |
| `docs/PROMPT_POLICY.md` | 보완 | — |
| `docs/mvp_scope.md` | R1 범위 추가 | — |

---

## 8. 시나리오 walkthrough (설계 검증용)

### 시나리오 A — 업무 스트레스

**사용자**: “오늘 회의에서 말이 안 통하는 느낌이 들었어. 끝나고 복도 형광등이 유난히 밝게 느껴졌어.”

| 단계 | 기대 |
|------|------|
| analyze_recording | topic: 회의 소통, key_phrases: ["말이 안 통한다", "복도 형광등"] |
| generate Q1 (association) | “형광등이 밝게 느껴진 순간, 그때 같이 떠오른 게 있나요?” |
| 사용자 답변 후 Q2 (contrast) | “회의 안에서의 느낌과 복도에 선 느낌이 같았나요?” |
| meaning_check | 사용 안 함 (risk low) |
| finalize | memory_type: observation + event, open_questions 유지 |

### 시나리오 B — 해석 위험 medium

**사용자**: “팀장이 또 늦게 와서 짜증 났어.” (맥락 부족)

| 단계 | 기대 |
|------|------|
| analyze_recording | interpretation_risk: medium |
| generate Q1 (meaning_check, 1회) | “짜증의 초점이 ‘지각’ 자체인가요, ‘반복’인가요?” |
| Q2 | association 또는 emotion_probe, meaning_check 금지 |

### 시나리오 C — 피로 신호

**사용자**: “모르겠어. 됐어.”

| 단계 | 기대 |
|------|------|
| validate_question / handler | needs_followup: false, REVIEW로 |

---

## 9. 다음 액션

1. 이 설계 문서 리뷰 (특히 MVP R1 범위와 질문 상한)
2. R1 구현 브랜치에서 `REFLECTION_AGENT_ENABLED` 플래그와 함께 질문 분리
3. 5~10개 실제 대화로 질문 유형 분포·meaning_check 비율 측정
4. 결과에 따라 `question_strategy.md` 우선순위 매트릭스 조정

구현은 **본 문서 합의 후** `cursor/reflection-agent-r1-c79e` 브랜치에서 시작한다.
