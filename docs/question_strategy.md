# Question Strategy

회고형 대화 에이전트가 생성하는 후속 질문의 **유형·목적·사용 조건**을 정의한다.  
질문 생성 로직(`conversation_to_memory/memory/question.py` 예정)과 프롬프트(`question_generation_prompt.txt` 예정)의 단일 기준 문서다.

---

## 1. 설계 원칙

1. **원문 충실** — 질문은 기록을 왜곡하지 않고 확장한다.
2. **유형 다양화** — `meaning_check`만 반복하지 않는다.
3. **사용자 프로필 정렬** — `user_conversation_profile.md`의 연상형·감각 중심 성향을 따른다.
4. **분리된 생성** — 요약/저장 프롬프트와 질문 생성 프롬프트를 분리한다.
5. **추적 가능** — 각 질문에 `question_mode`를 기록한다.

---

## 2. 질문 유형 분류

### 2.1 meaning_check — 의미·기록 확인

| 항목 | 내용 |
|------|------|
| **목적** | 요약·강조 포인트가 사용자 의도와 일치하는지 확인 |
| **사용 조건** | 해석 여지가 있거나, `interpretation_risk` ≥ medium |
| **예시** | “민원 전화 자체보다 ‘기다리는 시간’이 더 힘들다고 기록해도 될까요?” |
| **피해야 할 상황** | 직전 질문도 meaning_check; 사용자가 이미 명확히 말함; 세션에서 이미 1회 사용 |

**제한 규칙 (필수)**

- 세션당 **최대 1회**
- 최근 3개 질문 중 meaning_check **0회 초과 금지** (즉 연속 불가)
- `interpretation_risk: low`이고 `unsupported_inferences`가 비어 있으면 **생성하지 않음**

---

### 2.2 emotion_probe — 감정 탐색

| 항목 | 내용 |
|------|------|
| **목적** | 원문에 감정 단서는 있으나 라벨이 불명확할 때 구체화 |
| **사용 조건** | 신체 반응·톤·부정어 등 `emotion_evidence` 후보가 있으나 `user_emotions`가 비거나 모호 |
| **예시** | “‘막막하다’고 하셨는데, 그게 답답함에 가까웠나요, 허탈함에 가까웠나요?” |
| **피해야 할 상황** | 감정 단서 없음; 사용자가 감정 질문에 짧게 거부; 코칭式 “그 감정을 어떻게 다루셨나요” |

**주의**: 두 선택지 모두 사용자 표현에서 파생할 것. 새 감정 단어를 만들지 않는다.

---

### 2.3 association — 연상 확장

| 항목 | 내용 |
|------|------|
| **목적** | 독서모임식 꼬리 질문으로 사고를 옆으로 확장 |
| **사용 조건** | `key_phrases`에 생생한 명사·비유·장면이 있음; `reflection_value` ≥ medium |
| **예시** | “‘복도 끝 형광등’이 떠올랐다고 하셨는데, 그 장면이 다른 기억의 무엇과 겹치나요?” |
| **피해야 할 상황** | 사용자가 사건 마무리 의사; 주제가 이미 충분히 구체적; 연상이 기록 목적과 무관하게 멀어짐 |

**우선순위**: 이 사용자 프로필에서 **가장 선호되는 유형**. meaning_check 대신 association을 우선 고려.

---

### 2.4 memory_link — 과거 기억 연결

| 항목 | 내용 |
|------|------|
| **목적** | `recent_context` 또는 `related_past_patterns`와의 사실적 연결 제안 |
| **사용 조건** | 최근 기록과 키워드·사람·프로젝트·감정 겹침이 명확 |
| **예시** | “지난주 팀장 회의 기록에도 ‘말이 안 통한다’는 표현이 있었는데, 이번이랑 같은 지점인가요?” |
| **피해야 할 상황** | 과거 기록 없음; 겹침이 억지; 연결을 확정적으로 단정 |

연결은 **질문**으로만 제시. “같은 패턴입니다”라고 쓰지 않는다.

---

### 2.5 value_probe — 가치·선호 탐색

| 항목 | 내용 |
|------|------|
| **목적** | 사용자가 이미 드러낸 trade-off·불편·선호의 축을 명확히 |
| **사용 조건** | 두 가지 이상 가치가 충돌하는 듯한 발화; 선택의 이유가 암시됨 |
| **예시** | “그때 더 신경 쓰인 건 속도였나요, 아니면 제대로 처리되는 느낌이었나요?” |
| **피해야 할 상황** | 가치 판단을 에이전트가 먼저 제시; 도덕적 평가; “옳은 선택” 유도 |

---

### 2.6 contrast — 대비·각도 전환

| 항목 | 내용 |
|------|------|
| **목적** | 같은 사건을 다른 시점·역할·조건에서 다시 보게 함 |
| **사용 조건** | 사건은 있으나 관찰이 한쪽면에 치우침 |
| **예시** | “그날 밤이랑 지금 이야기할 때, 그 상황에서 가장 선명한 게 달라졌나요?” |
| **피해야 할 상황** | 사건 자체가 아직 불명확 (먼저 사실 확인); 대비가 인위적 |

---

### 2.7 future_reflection — 미래 회고 각도

| 항목 | 내용 |
|------|------|
| **목적** | 나중에 다시 읽을 때 남기고 싶은 초점을 사용자가 고르게 함 |
| **사용 조건** | `reflection_value` ≥ medium; 대화가 어느 정도 열림; 저장 직전 보조 질문 |
| **예시** | “한 달 뒤 다시 읽는다면, 오늘 말 중 어떤 부분이 가장 먼저 떠오르면 좋겠나요?” |
| **피해야 할 상황** | 미래 감정·행동 계획 예측; “앞으로 어떻게 하실 건가요”; 자기계발 목표 설정 |

---

### 2.8 archive_decision — 저장 범위·형태 결정

| 항목 | 내용 |
|------|------|
| **목적** | 무엇을 `memory_candidate`에 넣을지, 무엇을 부수적으로 둘지 사용자가 결정 |
| **사용 조건** | `emerging_themes`가 2개 이상; 한 세션에 여러 기억 후보 |
| **예시** | “오늘 이야기 중 ‘용역업체 실수’와 ‘기다림의 시간’ 중 어떤 걸 이번 기록의 중심으로 둘까요?” |
| **피해야 할 상황** | 단일 사건·단일 테마로 이미 명확; meaning_check와 중복 (기록 문구 확인만 반복) |

`archive_decision`은 **구조 선택**이고, `meaning_check`는 **문구 동의**다. 둘을 같은 세션에 쓰지 않는다.

---

## 3. 질문 모드 선택 로직 (개념)

질문 생성 전 분석 단계에서 다음 신호를 추출한다.

| 신호 | 설명 |
|------|------|
| `topic` | 핵심 주제 (1문장) |
| `emotion` | 감지된 감정 + 근거 유무 |
| `unresolved_point` | 미완성·모호·자기모순처럼 보이는 지점 |
| `possible_memory_value` | 장기 기억 후보 가치 (`low` / `medium` / `high`) |
| `question_mode` | 이번에 생성할 질문 유형 |

### 3.1 우선순위 매트릭스 (요약)

```text
interpretation_risk ≥ medium AND meaning_check 미사용
  → meaning_check (1회 한정)

unresolved_point 있음 AND 감정 단서 있음
  → emotion_probe 또는 association

recent_context 유사 AND memory_link 미사용
  → memory_link

key_phrases 생생 AND reflection_value ≥ medium
  → association (최우선)

emerging_themes ≥ 2
  → archive_decision

사건 명확 + 관찰 한쪽면
  → contrast

저장 직전 + 열린 대화
  → future_reflection

위에 해당 없음
  → association 또는 contrast (meaning_check 금지)
```

### 3.2 meaning_check 억제 규칙 (코드·프롬프트 공통)

```python
# 개념적 의사코드 — 구현은 reflection_agent_change_plan.md 참고

def can_use_meaning_check(session: QuestionSession) -> bool:
    if session.meaning_check_count >= 1:
        return False
    if session.last_question_mode == "meaning_check":
        return False
    if session.draft.interpretation_risk == "low":
        return False
    if not session.draft.unsupported_inferences:
        return False
    return True
```

---

## 4. 좋은 질문 / 나쁜 질문

### 4.1 공통 품질 기준

| 좋음 | 나쁨 |
|------|------|
| 사용자 표현 인용 | 일반론적 자기계발 질문 |
| 열린 확장 (연상·대비) | 닫힌 예/아니오만 반복 |
| 사실·관찰 중심 | 가치 판단·조언 요청 |
| 한 번에 한 가지 초점 | 여러 질문을 한 문장에 |
| 피로 신호 시 중단 | “조금만 더” 반복 |

### 4.2 유형별 예시 확장

**association**

- 좋음: “‘종이 냄새’가 나는 순간이 있다고 하셨는데, 그게 어떤 장면과 붙어 있나요?”
- 나쁨: “그 경험의 의미는 무엇인가요?”

**memory_link**

- 좋음: “예전에 적으신 ○○ 기록에도 ‘책임이 모호하다’는 말이 있었는데, 이번 상황과 같은 느낌인가요?”
- 나쁨: “또 같은 실수를 반복하고 계시네요. 왜 그럴까요?”

**contrast**

- 좋음: “회의 중에 느낀 것과, 지금 다시 말할 때 느낌이 같은가요?”
- 나쁨: “그때는 부정적이었지만 지금은 긍정적으로 바뀌었죠?”

---

## 5. 세션 상태 추적

질문 생성 시 세션에 유지할 메타데이터:

| 필드 | 용도 |
|------|------|
| `questions_asked` | 이번 세션 질문 수 |
| `question_modes_used` | 유형 목록 (중복·연속 방지) |
| `meaning_check_count` | meaning_check 횟수 |
| `last_question_mode` | 직전 유형 |
| `user_fatigue_signals` | 짧은 답, 거부, 중단 키워드 |

피로 신호가 감지되면 `needs_followup: false`로 전환하고 REVIEW로 진행한다.

---

## 6. 출력 스키마 (질문 생성 단계)

질문 전용 API/함수의 JSON 출력 예:

```json
{
  "topic": "팀 회의 후 불편함",
  "emotion": {
    "labels": ["답답함"],
    "evidence_strength": "medium"
  },
  "unresolved_point": "말이 안 통한다는 느낌의 구체적 순간",
  "possible_memory_value": "medium",
  "question_mode": "association",
  "followup_question": "‘말이 안 통한다’고 하셨는데, 그때 떠올랐던 특정 장면이나 소리가 있나요?",
  "needs_followup": true,
  "reasoning": "감정 단서는 있으나 장면이 얇음. 연상형 확장이 적합."
}
```

`reasoning`은 디버그·로그용. Telegram 사용자에게는 보내지 않는다.

---

## 7. 기존 프롬프트와의 관계

| 현재 | 변경 후 |
|------|---------|
| `memory_archive_system_prompt.txt`에 후속 질문 규칙 포함 | 요약 전용으로 축소; `needs_followup`/`followup_question` 제거 또는 비활성 |
| `analyze_recording()` 단일 호출 | `analyze_recording()` + `generate_question()` 분리 |
| `fidelity.py`가 요약만 검증 | 질문 품질 검증 함수 추가 (`validate_question()`) |

금지 표현·성장 서사 규칙은 **양쪽 프롬프트 모두**에 유지한다.

---

## 8. 테스트 관점

| 케이스 | 기대 |
|--------|------|
| interpretation_risk: low | meaning_check 생성 안 함 |
| meaning_check 1회 후 | 다음 질문은 association 등 |
| 감정 단서 없음 | emotion_probe 생성 안 함 |
| recent_context 비어 있음 | memory_link 생성 안 함 |
| “됐어” / “모르겠어” | needs_followup: false |
| 생생한 key_phrase | association 우선 |

구현 시 `tests/test_question_generation.py`에 위 케이스를 추가한다.
