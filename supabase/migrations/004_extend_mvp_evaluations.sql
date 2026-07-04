-- 3차 MVP 평가 확장: 회고 가치 / 질문 품질 분리 필드

ALTER TABLE mvp_evaluations
    ADD COLUMN IF NOT EXISTS reflection_judgment text,
    ADD COLUMN IF NOT EXISTS question_quality_grade text,
    ADD COLUMN IF NOT EXISTS period_start date,
    ADD COLUMN IF NOT EXISTS period_end date,
    ADD COLUMN IF NOT EXISTS failure_count integer,
    ADD COLUMN IF NOT EXISTS pattern_cards jsonb;

ALTER TABLE mvp_evaluations
    DROP CONSTRAINT IF EXISTS mvp_evaluations_judgment_check;

ALTER TABLE mvp_evaluations
    ADD CONSTRAINT mvp_evaluations_judgment_check
        CHECK (
            final_judgment IN (
                'fail',
                'not_ready',
                'partial_success',
                'conditional_success',
                'success',
                'strong_success'
            )
        );

ALTER TABLE mvp_evaluations
    DROP CONSTRAINT IF EXISTS mvp_evaluations_question_quality_grade_check;

ALTER TABLE mvp_evaluations
    ADD CONSTRAINT mvp_evaluations_question_quality_grade_check
        CHECK (
            question_quality_grade IS NULL
            OR question_quality_grade IN ('excellent', 'good', 'fair', 'poor')
        );

CREATE INDEX IF NOT EXISTS mvp_evaluations_period_start_idx
    ON mvp_evaluations (period_start DESC);
