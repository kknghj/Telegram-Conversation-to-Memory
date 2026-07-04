-- AI 질문/해석 실패 스냅샷 (canonical: data/evaluation/interpretation_failures.jsonl)

CREATE TABLE IF NOT EXISTS interpretation_failures (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    failure_key text UNIQUE NOT NULL,
    occurred_at timestamptz NOT NULL,
    conversation_id text NOT NULL,
    source_memory_file text NULL,
    message_index integer NULL,
    failure_type text NOT NULL,
    severity text NOT NULL DEFAULT 'medium',
    context jsonb NOT NULL DEFAULT '[]'::jsonb,
    user_correction text NOT NULL DEFAULT '',
    assistant_output text NOT NULL DEFAULT '',
    expected_behavior text NULL,
    root_cause text NULL,
    fixed_rule text NULL,
    rule_candidate text NULL,
    recurrence_risk text NULL,
    prevented_by_rule boolean NULL,
    raw jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT interpretation_failures_type_check
        CHECK (
            failure_type IN (
                'repeated_question',
                'korean_misparse',
                'correction_ignored',
                'memory_unavailable_ignored',
                'inappropriate_positive_reframe'
            )
        ),

    CONSTRAINT interpretation_failures_severity_check
        CHECK (severity IN ('low', 'medium', 'high')),

    CONSTRAINT interpretation_failures_recurrence_risk_check
        CHECK (
            recurrence_risk IS NULL
            OR recurrence_risk IN ('low', 'medium', 'high')
        )
);

CREATE INDEX IF NOT EXISTS interpretation_failures_occurred_at_idx
    ON interpretation_failures (occurred_at DESC);

CREATE INDEX IF NOT EXISTS interpretation_failures_failure_type_idx
    ON interpretation_failures (failure_type);

CREATE INDEX IF NOT EXISTS interpretation_failures_conversation_id_idx
    ON interpretation_failures (conversation_id);

CREATE OR REPLACE FUNCTION interpretation_failures_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS interpretation_failures_updated_at ON interpretation_failures;

CREATE TRIGGER interpretation_failures_updated_at
    BEFORE UPDATE ON interpretation_failures
    FOR EACH ROW
    EXECUTE FUNCTION interpretation_failures_set_updated_at();

ALTER TABLE interpretation_failures ENABLE ROW LEVEL SECURITY;
