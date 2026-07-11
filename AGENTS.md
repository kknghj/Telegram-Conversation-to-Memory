# Project Instructions

## Required context at the start of every task

Before analyzing, planning, editing, or implementing anything in this repository:

1. Read `docs/vision.md` completely.
2. Read `docs/future_roadmap.md` completely.
3. Read `docs/validation_plan.md` completely.
4. Identify:
   - the long-term product direction,
   - the current roadmap phase,
   - the current validation stage and its latest recorded result,
   - the invariant product principles relevant to the task,
   - the next incomplete work item supported by repository evidence.
5. Briefly state which vision, roadmap, and validation considerations affect the task before making material changes.

Do not treat the current memory-archive MVP as the final product. It is the trusted memory substrate for the long-term goal: a memory-based personal AI agent that prepares grounded, interesting content for the user.

## Product decision principles

All work must preserve these principles unless the user explicitly changes the product direction:

- The user's original words are the highest-priority evidence.
- Separate facts, quotations, and AI interpretation.
- Do not invent growth narratives, psychological conclusions, positive reframing, or coaching advice.
- Keep user-approved memories separate from internal candidates and drafts.
- Do not publish generated content immediately; weak content may remain pending or be discarded.
- Optimize for groundedness, trust, curiosity, and reading value, not productivity coaching or engagement volume.
- Distinguish clearly between the current archive MVP, the next roadmap phase, and the long-term content-publishing agent vision.
- Preserve the responsibility boundaries represented by Archivist, Reporter, Editor, Editor-in-Chief, and Feedback Steward, even if the code uses different implementation units.

## Progress tracking source of truth

Use these documents together as the project control plane:

- `docs/vision.md`: stable product philosophy and long-term destination. Do not use it as a task checklist.
- `docs/future_roadmap.md`: implementation progress, phase status, completed capabilities, current phase, and the next implementation milestone.
- `docs/validation_plan.md`: validation progress, evidence, pass/conditional-pass/fail decisions, unresolved risks, and the next validation action.

Do not create a separate competing progress document unless the user explicitly requests one.

At the end of any task that materially changes implementation progress or validation evidence:

1. Update `docs/future_roadmap.md` when a capability starts, changes status, is completed, or changes the recommended next implementation milestone.
2. Update `docs/validation_plan.md` when new evidence is collected, a criterion changes, a stage changes status, or the next validation action changes.
3. Record only progress supported by code, tests, stored data, deployment state, or explicit user validation.
4. Use explicit status labels: `not_started`, `in_progress`, `blocked`, `conditional_pass`, `passed`, or `superseded`.
5. Include the evidence and date for `conditional_pass`, `passed`, and `superseded` decisions.
6. Keep exactly one clearly labeled current implementation milestone and one clearly labeled next validation action.
7. Do not mark roadmap work complete merely because code was written; verification appropriate to the change must also pass.
8. Do not describe future capabilities as already implemented.

If implementation and validation progress diverge, record them separately. For example, a feature may be implemented in the roadmap while its validation stage remains `in_progress` or `conditional_pass`.

## Before making changes

If a requested change conflicts with `docs/vision.md`, `docs/future_roadmap.md`, or `docs/validation_plan.md`, do not silently choose one side. Explain the conflict and ask for direction when it would materially change the product.

For documentation changes, inspect related documents as one system and remove or label contradictory legacy descriptions. Preserve historical evidence, but do not let historical plans appear to be current instructions.

## After making changes

Check that the result:

- remains grounded in original user evidence,
- does not introduce coaching or unsupported interpretation,
- fits the intended roadmap and validation stage,
- does not describe future capabilities as already implemented,
- updates roadmap or validation status when the evidence warrants it,
- keeps related documentation consistent when product philosophy changes.

