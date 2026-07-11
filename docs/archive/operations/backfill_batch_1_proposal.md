# Backfill Batch 1 Proposal

> 상태: `superseded` — 사용자 승인과 Supabase 반영이 끝난 일회성 운영 기록입니다. 검증 결론은 `../../validation_stage_0_1_decisions.md`를 따릅니다. 격리일: 2026-07-11.

작성일: 2026-07-09  
상태: 사용자 승인 후 Supabase 반영 완료

## 목적

`fidelity.py`의 확장된 신호 기준을 과거 기억에 다시 적용해 누락된 공식 필드를 보강한다.

이번 배치는 DB 수정 전 사용자 확인용 제안서로 작성되었고, 2026-07-09 사용자 승인 후 Supabase에 반영했다.

## 적용 기준

DB에 `reflection_seed_signal`, `oriented_marker`, `human_ideal_marker`라는 필드를 추가하지 않는다. 이들은 `fidelity.py` 내부 신호로만 본다.

백필 대상 공식 필드는 다음이다.

- `raw_memory.reflection_seed_candidate`
- `raw_memory.memory_type`
- `raw_memory.reflection_value`
- `raw_memory.temporal_status`
- `raw_memory.value_tags`
- `raw_memory.projects`

필요하면 top-level `projects` 컬럼도 `raw_memory.projects`와 맞춘다.

---

## 1차 백필 후보

### 1. 도구 개발 아이디어

ID: `a1310826-bbb9-443d-bb3e-e114f9f77958`

현재값:

```json
{
  "memory_type": "event",
  "reflection_value": "medium",
  "reflection_seed_candidate": null,
  "temporal_status": null,
  "value_tags": null,
  "projects": []
}
```

제안값:

```json
{
  "memory_type": "reflection_seed",
  "reflection_value": "high",
  "reflection_seed_candidate": true,
  "temporal_status": "current",
  "value_tags": ["사용자 시간 절약", "생산성"],
  "projects": []
}
```

근거:

- `만들고 싶다` 신호가 명확하다.
- 서울시 공무원에게 도움될 도구, 요식적 잡일 처리, 업무 절차 축소라는 반복 가능한 개발/업무 철학이 있다.

### 2. 토스 미니앱 제작 강의

ID: `13e43ae6-60c7-40d6-a321-194e51cdc148`

현재값:

```json
{
  "memory_type": "event",
  "reflection_value": "medium",
  "reflection_seed_candidate": null,
  "temporal_status": null,
  "value_tags": null,
  "projects": []
}
```

제안값:

```json
{
  "memory_type": "reflection_seed",
  "reflection_value": "high",
  "reflection_seed_candidate": true,
  "temporal_status": "mixed",
  "value_tags": ["사용자 시간 절약", "편의성", "다크패턴 거부", "불안 마케팅 거부"],
  "projects": ["GPTERS", "Harness", "Cursor", "토스 미니앱"]
}
```

근거:

- `만들고 싶`, `거리낌`, `낭비한다는 생각` 신호가 모두 있다.
- 사용자의 앱/도구 선택 기준이 분명하다.
- `7월 말부터 들을 강의`, `신청했다`, `수강 변경했다`가 섞여 있어 `mixed`가 적절하다.

### 3. 인공지능 자동화 사용

ID: `6025dec6-28ca-4fce-9225-9da93f564b74`

현재값:

```json
{
  "memory_type": "observation",
  "reflection_value": "medium",
  "reflection_seed_candidate": null,
  "temporal_status": null,
  "value_tags": null,
  "projects": []
}
```

제안값:

```json
{
  "memory_type": "observation",
  "reflection_value": "medium",
  "reflection_seed_candidate": true,
  "temporal_status": "current",
  "value_tags": ["생산성"],
  "projects": ["Codex", "Cursor"]
}
```

근거:

- 효율적으로 AI를 쓰고 있는지 의심하고, 수동 복붙/검증 흐름을 자동화하고 싶다는 반복 가능한 작업 방식 기준이 있다.
- 다만 하나의 사건/관찰 성격도 남아 있으므로 `memory_type`은 `observation` 유지가 보수적이다.

### 4. 서울시 공무원과 연주

ID: `4d8c34c3-6949-4bf3-9686-76ec3fd4d989`

현재값:

```json
{
  "memory_type": "observation",
  "reflection_value": "medium",
  "reflection_seed_candidate": null,
  "temporal_status": null,
  "value_tags": null,
  "projects": []
}
```

제안값:

```json
{
  "memory_type": "reflection_seed",
  "reflection_value": "high",
  "reflection_seed_candidate": true,
  "temporal_status": "current",
  "value_tags": [],
  "projects": []
}
```

근거:

- `어떤 공무원이 되고 싶냐`, 직장 생활을 연기로 보는 감각, 책임감/사회성/복종/순진한 척에 대한 인식이 있다.
- `human ideal marker`에 가까운 장기 직업관 재료다.

### 5. AI 프로젝트와 개인 감정

ID: `45d416af-6b8f-497d-8cc7-72dc5ef6cd71`

현재값:

```json
{
  "memory_type": "event",
  "reflection_value": "medium",
  "reflection_seed_candidate": null,
  "temporal_status": null,
  "value_tags": null,
  "projects": ["AI 프로젝트"]
}
```

제안값:

```json
{
  "memory_type": "reflection_seed",
  "reflection_value": "medium",
  "reflection_seed_candidate": true,
  "temporal_status": "mixed",
  "value_tags": ["사용자 시간 절약"],
  "projects": ["AI 프로젝트"]
}
```

근거:

- `놓고 싶지 않다`, `구축해보고 싶다`, `시간낭비한다는 생각`이 있다.
- 프로젝트를 지속하고 싶은 마음, 금전적 보상에 따른 조급함, 불안할 때 아무것도 못하는 패턴이 장기 재료다.
- `reflection_value`는 이미 medium이므로 무리하게 high로 올리지 않는다.

### 6. 프로그램 개발과 AI의 영향

ID: `a427fbad-bdd6-4f1a-9dfc-879e5750ca8b`

현재값:

```json
{
  "memory_type": "event",
  "reflection_value": "medium",
  "reflection_seed_candidate": null,
  "temporal_status": null,
  "value_tags": null,
  "projects": ["필사 줄바꿈 변환기"]
}
```

제안값:

```json
{
  "memory_type": "reflection_seed",
  "reflection_value": "high",
  "reflection_seed_candidate": true,
  "temporal_status": "mixed",
  "value_tags": ["사용자 시간 절약"],
  "projects": ["필사 줄바꿈 변환기"]
}
```

근거:

- "많은 사람들에게 도움이 되는 걸 확인하고 싶다"는 제작 지향이 있다.
- AI 때문에 결과물을 먼저 만들 수 있게 되었고 공부의 순서가 바뀌었다는 개발/학습 철학이 드러난다.

### 7. 프로젝트 진행

ID: `0de8c1b9-6072-4380-86f7-262d36ec206c`

현재값:

```json
{
  "memory_type": "event",
  "reflection_value": "medium",
  "reflection_seed_candidate": null,
  "temporal_status": null,
  "value_tags": null,
  "projects": ["텔레그램 봇 프로젝트", "노션 이모지 자동화 프로젝트"]
}
```

제안값:

```json
{
  "memory_type": "reflection_seed",
  "reflection_value": "medium",
  "reflection_seed_candidate": true,
  "temporal_status": "current",
  "value_tags": [],
  "projects": ["Telegram Conversation to Memory", "노션 이모지 자동화 프로젝트"]
}
```

근거:

- 시작한 것을 끝까지 보지 못하는 패턴, 이번 프로젝트 결과물을 눈으로 확인하고 싶다는 지향이 있다.
- 프로젝트 지속성에 대한 장기 재료다.

### 8. 식생활 교육 자동화

ID: `be778346-69f3-44e8-a2d3-01fa9c54120b`

현재값:

```json
{
  "memory_type": "event",
  "reflection_value": "medium",
  "reflection_seed_candidate": null,
  "temporal_status": null,
  "value_tags": null,
  "projects": []
}
```

제안값:

```json
{
  "memory_type": "reflection_seed",
  "reflection_value": "medium",
  "reflection_seed_candidate": true,
  "temporal_status": "future",
  "value_tags": ["사용자 시간 절약", "생산성"],
  "projects": ["식생활교육 자동화"]
}
```

근거:

- 시간이 많이 잡아먹는 일을 자동화하고 싶다는 명확한 업무 자동화 기준이 있다.
- 아직 할 예정인 작업이 많아 `future`가 적절하다.

### 9. 식생활교육 자동화 프로젝트

ID: `4d74b298-5244-4a71-9667-c3de47f1c816`

현재값:

```json
{
  "memory_type": "event",
  "reflection_value": "medium",
  "reflection_seed_candidate": null,
  "temporal_status": null,
  "value_tags": null,
  "projects": ["식생활교육 자동화 프로젝트", "노션 프로젝트"]
}
```

제안값:

```json
{
  "memory_type": "event",
  "reflection_value": "medium",
  "reflection_seed_candidate": false,
  "temporal_status": "mixed",
  "value_tags": [],
  "projects": ["식생활교육 자동화 프로젝트", "노션 프로젝트"]
}
```

근거:

- 자동화 자체보다 프로젝트 추가로 인한 조급함, 업무 생각 침범, 자신감 부족이 중심이다.
- 장기 후보의 직접 seed로 올리기보다 temporal/status 보강만 하는 것이 보수적이다.

### 10. AI와 집안일

ID: `08de363f-9cbc-4abc-8727-cbe5af553a20`

현재값:

```json
{
  "memory_type": "event",
  "reflection_value": "medium",
  "reflection_seed_candidate": null,
  "temporal_status": null,
  "value_tags": null,
  "projects": []
}
```

제안값:

```json
{
  "memory_type": "event",
  "reflection_value": "medium",
  "reflection_seed_candidate": false,
  "temporal_status": "mixed",
  "value_tags": ["편의성"],
  "projects": []
}
```

근거:

- AI가 집안일을 대신해줬으면 한다는 현재 바람과, 빨래를 방치했던 과거 장면이 함께 있다.
- 자동화/편의성 취향은 있으나 장기 판단 기준으로 단정하기엔 약하므로 seed 후보는 false가 적절하다.

---

## 반영 방식

각 기억의 `raw_memory` 안 공식 필드만 업데이트했다.

추가로 `projects` top-level 컬럼은 제안값에 맞췄다.

이번 배치에서는 `event_summary`, `memory_candidate`, `conversation` 원문은 수정하지 않았다.

## 반영 후 집계

| 항목 | 반영 후 |
|---|---:|
| 배치 반영 건수 | 10 |
| `temporal_status` 보유 기억 | 23/105 |
| `reflection_seed_candidate` 보유 기억 | 23/105 |
| `value_tags` 보유 기억 | 23/105 |
| `reflection_seed_candidate=true` | 10 |
| `memory_type=reflection_seed` | 20 |
| `reflection_value=high` | 9 |
| `reflection_value=medium` | 74 |
| `reflection_value=low` | 22 |

`temporal_status` 분포:

| 값 | 건수 |
|---|---:|
| `current` | 5 |
| `future` | 2 |
| `mixed` | 5 |
| `past` | 11 |

`value_tags` 분포:

| 태그 | 건수 |
|---|---:|
| 사용자 시간 절약 | 5 |
| 생산성 | 3 |
| 편의성 | 2 |
| 다크패턴 거부 | 1 |
| 불안 마케팅 거부 | 1 |
