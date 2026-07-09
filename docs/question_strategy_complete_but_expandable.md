# Question Strategy: Complete but Expandable

## 목적

이 문서는 `docs/question_strategy.md`의 보충 기준이다.

2026-07-09 분석에서 최신 live 기억의 후속 질문 생성률이 급격히 낮아진 원인이 확인되었다. 핵심은 질문 생성기가 정확한 요약을 `질문 불필요`로 과하게 해석했다는 점이다.

따라서 다음 원칙을 추가한다.

```text
정확한 요약은 meaning_check를 줄이는 근거다.
정확한 요약은 association/contrast/value_probe를 금지하는 근거가 아니다.
```

## 새 상태: complete_but_expandable

`complete_but_expandable`은 정보는 충분하지만, 사용자가 새 생각으로 이어질 수 있는 원문 손잡이를 남긴 상태다.

이 상태에서는 다음과 같이 판단한다.

| 항목 | 판단 |
| --- | --- |
| meaning_check | 생성하지 않음 |
| association | 가능 |
| contrast | 가능 |
| value_probe | 가능 |
| archive_decision | 여러 중심 후보가 있을 때 가능 |
| positive reframe | 계속 금지 |
| 피로 신호 후 질문 | 계속 금지 |

## 감지 신호

다음이 있으면 `complete_but_expandable` 후보로 본다.

- 생생한 `key_phrases`
- `기억이 났다`, `떠올랐다` 같은 기억 재등장 표현
- 아쉬움, 거리낌, 열등감, 불확실성처럼 원문 근거가 있는 감정/판단
- 가치 판단, 기준, 원하는 방향, 만들고 싶은 것
- 후속질문, 새로운 관점, 사용 만족도에 대한 메타 피드백

## 허용되는 질문

질문은 원문을 한 걸음만 확장해야 한다.

좋은 형식:

- 원문 표현을 인용한다.
- 사용자가 이미 말한 두 축 사이의 대비를 묻는다.
- 나중에 다시 읽을 때 남기고 싶은 초점을 묻는다.
- 사용자가 드러낸 가치 판단을 더 정확히 남기기 위한 선택지를 준다.

나쁜 형식:

- 감정을 긍정으로 전환한다.
- 교훈, 극복, 성장, 해결책을 묻는다.
- 원문에 없는 심리 원인을 가정한다.
- 한 문장에 여러 질문을 넣는다.

## 예시

### 승진과 열등감

원문 손잡이:

```text
남들보다 뒤떨어진다는 열등감
```

허용 질문:

```text
'열등감'이 자리를 차지했다는 표현에서, 비교의 기준이 가장 선명해진 순간이 있었나요?
```

### 음주와 스트레스 해소

원문 손잡이:

```text
술 마시는 걸로 스트레스를 푸는 것을 자제해야 하는데...
```

허용 질문:

```text
'자제해야 하는데'라는 말에서, 이번 기록에 남기고 싶은 건 아쉬움 쪽인가요 아니면 스트레스 푸는 방식에 대한 경계 쪽인가요?
```

### 질문 생성 만족도 하락

원문 손잡이:

```text
이전에는 새로운 관점의 질문이 새로운 생각으로 이어졌는데
```

허용 질문:

```text
예전에 새로운 생각으로 이어졌던 질문은 어떤 방식이었는지 떠오르는 예가 있나요?
```

## 구현 연결

- `conversation_to_memory/memory/question.py`
  - `EXPANSION_SIGNAL_KEYWORDS`
  - `has_reflective_expansion_signal()`
  - `build_grounded_expansion_question()`
- `conversation_to_memory/prompts/question_generation_prompt.txt`
  - `complete_but_expandable`
  - skip reason taxonomy
- `tests/test_question_generation.py`
  - `test_complete_but_expandable_recovers_grounded_question`
  - `test_no_reflective_handle_stays_skipped`
  - `test_reflective_expansion_signal_detects_product_feedback`

## 검증 기준

다음 20개 live 신규 기억에서 확인한다.

| 지표 | 목표 |
| --- | ---: |
| 질문 포함 세션 | 최소 6건 |
| positive reframe 위험 질문 전송 | 0건 |
| 피로 신호 뒤 추가 질문 | 0건 |
| 사용자가 별로라고 느낀 질문 | 20% 이하 |
| 질문이 기억을 풍부하게 만든 세션 | 질문 포함 세션의 60% 이상 |
