# Stage 2 Validation — Mini-era window (2026-07-09 → pre-luna)

- Evaluated: 2026-07-16
- Window: `memories.created_at >= 2026-07-09` and `< 2026-07-16 07:30+00` (first luna production traces)
- Model: `gpt-4o-mini` (decision_traces in window)
- Source: Supabase `memories` / `drafts` / `decision_traces` / `interpretation_failures`
- Raw aggregate: `reports/validation/stage2_window_20260709_pre_luna.json`
- Status: **`conditional_pass`** (window evaluation complete; seed 후보 사용자 검토로 품질 축 보강; not `passed`)
- Seed review: `reports/validation/stage2_seed_review_20260709_pre_luna.json` — 납득 6/7 (86%)

## Scope note

This evaluates the **post–question-recovery, pre-luna** live era only. It does not close luna live observation. Question sessions are counted from **assistant turns in saved conversations**, not only `question_outcome=question_sent` traces (trace schema was incomplete early in the window).

## Sample

| Metric | Value |
|--------|------:|
| Approved memories in window | 22 |
| Drafts (saved / cancelled) | 22 / 1 |
| Sessions with ≥1 assistant question | 17 |
| Sessions without questions | 5 |
| `reflection_seed_candidate=true` | 7 / 22 |
| `open_questions` nonempty | 0 / 22 |
| `reflection_seed` text nonempty | 0 / 22 |
| `key_phrases` nonempty | 22 / 22 |
| `emerging_themes` nonempty | 0 / 22 |

Entry checks for this window: question sessions ≥10 ✓, total archive ≥100 ✓.

## Pass criteria scorecard

| Criterion | Result | Evidence |
|-----------|--------|----------|
| Question sessions: ≥60% memory material enriched | **Pass** — 16/17 (94%) | Substantive user reply after ≥1 question |
| Reject/fatigue signal ≤20% | **Fail** — 4/17 (24%) | `패스` 3 sessions + explicit complaint 1 |
| `meaning_check` repeat failure = 0 | **Fail** | Dostoevsky second compare question; logged `redundant_question` |
| Positive-recall-after-negative-emotion failure = 0 | **Pass** | No clear instance in window |
| Bad question types decrease after user rejection | **Partial** | `low_salience_anchor` / category mismatch (07-11) did not recur post 07-12; coaching-style asks still common |
| Seed candidates: ≥70% long-term material (user) | **Pass** — 6/7 (86%) | User review 2026-07-16; S6 discard |

## Qualitative findings

### What worked

- Many questions pulled concrete scenes and judgments (초혜/직장 대비, 덕질 에피소드, 러닝 후 개운함, 토스 미니앱 눈에 띄는 요소, 자유 일상 목록).
- After 07-12 quality fix: `redundant_question` candidate rejected in traces (07-14 겸직/과장); `tools` separation appears (GPT/Codex/Telegram).
- Second-question gate fires (`max_questions_reached`, `no_new_unresolved_point`).

### What failed or stayed weak

1. **Known 07-11 failures (pre-fix)**  
   - Dostoevsky: already-answered link re-asked → `패스`.  
   - Summer menu: low-salience 콩국수 anchor + category mismatch → user “맥락에 맞지 않은 질문”.

2. **Coaching tone (6/17 question sessions)**  
   Examples: “대비하기 위해 어떤 준비”, “어떤 전략을 세우고 싶으신가요”, “구체적인 변화나 시도”, “긍정적인 영향”.  
   These often still got answers, so enrichment rate looks high while product feel drifts toward coaching — against vision/Stage 2 intent.

3. **Seed payload fields still empty; candidate quality accepted**  
   Stored `open_questions` / `reflection_seed` text stay empty (flag-only). User review nonetheless accepted 6/7 candidates as long-term material (S6 겸직 허가 제외). So **candidate selection quality passes 70%**, while **structured seed fields remain unfilled**.

4. **Fatigue**  
   Three `패스` (Dostoevsky Q2, free-life Q2, human-vs-bot Q1) plus one explicit quality complaint → 24% > 20% gate.

### Pre vs post 07-12

| | Pre-fix (≤07-11) | Post-fix (≥07-12) |
|--|--:|--:|
| Question sessions | 5 | 12 |
| Logged question-quality failures | 2 (`redundant_question`, `low_salience_anchor`) | 0 new of those types |
| Coaching-marked sessions | 0 of 5 | 6 of 12 |

Fix reduced the recorded failure modes; coaching drift became the dominant residual risk in this mini window.

## Decision

- **Window verdict:** `conditional_pass`
- **Strengthened by:** seed 후보 사용자 납득 6/7 (86%) ≥70%
- **Why not `passed`:** fatigue >20%, documented meaning_check/redundant failure in-window, seed payload fields still empty, coaching-style questions still frequent.
- **Why not `fail`:** enrichment strong, post-fix gates work, key phrases present, seed *candidate* quality user-validated.
- **Does not replace** luna live Stage 2 closure.

## Next validation action

Keep observing **`gpt-5.6-luna` live** for: coaching-tone rate, `패스`/complaint rate, whether `open_questions` / `reflection_seed` text fill, and recurrence of redundant / low-salience asks. Target ≥10 luna question sessions before Stage 2 `passed` reconsideration.

## Seed 후보 7건 사용자 검토 — `passed` (품질 축)

- 상태: `passed` (2026-07-16)
- 결과: 납득 6 / 부분 0 / 아님 1
- 납득: S1 러닝 대비, S2 가치관·상금, S3 제품 거리낌·완성, S4 사무실 눈치, S5 자유 일상, S7 에너지 배분
- 아님: S6 겸직 허가·과장 걱정
- S7 메모(제품 원칙): 사용자가 생산성/효율을 **원문으로 직접 말한 경우**, 그것을 seed로 남기는 것은 AI 생산성 코칭과 동일시하지 않는다.
- 근거: `reports/validation/stage2_seed_review_20260709_pre_luna.json`

## Remaining user taste checks (optional)

1. Whether coaching-toned questions felt like coaching in live use.
2. Whether “enriched” answers felt worth the second question when the first already helped.
