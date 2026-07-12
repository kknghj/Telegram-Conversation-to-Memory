-- Expand interpretation_failures.failure_type CHECK for question-quality taxonomy.
-- Adds: redundant_question, low_salience_anchor, category_mismatch, meta_feedback_leaked_into_memory
-- Keeps existing types from 003 + 009.

ALTER TABLE interpretation_failures
    DROP CONSTRAINT IF EXISTS interpretation_failures_type_check;

ALTER TABLE interpretation_failures
    ADD CONSTRAINT interpretation_failures_type_check
        CHECK (
            failure_type IN (
                'repeated_question',
                'korean_misparse',
                'correction_ignored',
                'correction_partial',
                'memory_unavailable_ignored',
                'inappropriate_positive_reframe',
                'value_hidden_by_event',
                'redundant_question',
                'low_salience_anchor',
                'category_mismatch',
                'meta_feedback_leaked_into_memory'
            )
        );
