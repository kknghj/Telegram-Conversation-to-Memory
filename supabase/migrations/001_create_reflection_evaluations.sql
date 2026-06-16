-- Reflection evaluation observation log (remote mirror of JSONL canonical source)

CREATE TABLE IF NOT EXISTS reflection_evaluations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id text NOT NULL,
    evaluated_at timestamptz NOT NULL,
    memory_count integer NOT NULL,
    card_id text NOT NULL,
    card_type text NOT NULL,
    accuracy text NOT NULL,
    interesting boolean NOT NULL DEFAULT false,
    revisit boolean NOT NULL DEFAULT false,
    evidence text NOT NULL,
    failure_type text NULL,
    user_comment text NULL,
    action text NOT NULL,
    raw jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT reflection_evaluations_evaluation_card_unique
        UNIQUE (evaluation_id, card_id),

    CONSTRAINT reflection_evaluations_accuracy_check
        CHECK (accuracy IN ('correct', 'partial', 'wrong')),

    CONSTRAINT reflection_evaluations_evidence_check
        CHECK (evidence IN ('sufficient', 'weak', 'wrong')),

    CONSTRAINT reflection_evaluations_action_check
        CHECK (action IN ('keep', 'revise', 'discard')),

    CONSTRAINT reflection_evaluations_failure_type_check
        CHECK (
            failure_type IS NULL
            OR failure_type IN (
                'SEARCH_FAILURE',
                'CONNECTION_FAILURE',
                'INTERPRETATION_FAILURE',
                'OVER_GENERALIZATION',
                'OBVIOUS_INSIGHT',
                'DATA_INSUFFICIENT',
                'DUPLICATED_CARD',
                'EVIDENCE_WEAK',
                'EVIDENCE_WRONG'
            )
        )
);

CREATE INDEX IF NOT EXISTS reflection_evaluations_evaluation_id_idx
    ON reflection_evaluations (evaluation_id);

CREATE INDEX IF NOT EXISTS reflection_evaluations_evaluated_at_idx
    ON reflection_evaluations (evaluated_at DESC);

CREATE OR REPLACE FUNCTION reflection_evaluations_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS reflection_evaluations_updated_at ON reflection_evaluations;

CREATE TRIGGER reflection_evaluations_updated_at
    BEFORE UPDATE ON reflection_evaluations
    FOR EACH ROW
    EXECUTE FUNCTION reflection_evaluations_set_updated_at();

-- Service-role client only; no public API exposure in this phase.
ALTER TABLE reflection_evaluations ENABLE ROW LEVEL SECURITY;
