-- MVP round evaluation snapshots (separate from per-card reflection_evaluations)

CREATE TABLE IF NOT EXISTS mvp_evaluations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id text UNIQUE NOT NULL,
    evaluation_type text NOT NULL,
    round integer NOT NULL,
    evaluated_at date NOT NULL,
    memory_count integer NOT NULL,
    previous_memory_count integer,
    new_memory_count integer,
    final_judgment text NOT NULL,
    score numeric,
    user_validated boolean NOT NULL DEFAULT false,
    user_validation_summary jsonb,
    top_insights jsonb,
    main_limitation text,
    next_milestone text,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT mvp_evaluations_type_check
        CHECK (evaluation_type IN ('mvp_round')),

    CONSTRAINT mvp_evaluations_judgment_check
        CHECK (
            final_judgment IN (
                'fail',
                'partial_success',
                'conditional_success',
                'success'
            )
        )
);

CREATE INDEX IF NOT EXISTS mvp_evaluations_round_idx
    ON mvp_evaluations (round);

CREATE INDEX IF NOT EXISTS mvp_evaluations_evaluated_at_idx
    ON mvp_evaluations (evaluated_at DESC);

CREATE OR REPLACE FUNCTION mvp_evaluations_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS mvp_evaluations_updated_at ON mvp_evaluations;

CREATE TRIGGER mvp_evaluations_updated_at
    BEFORE UPDATE ON mvp_evaluations
    FOR EACH ROW
    EXECUTE FUNCTION mvp_evaluations_set_updated_at();

ALTER TABLE mvp_evaluations ENABLE ROW LEVEL SECURITY;
