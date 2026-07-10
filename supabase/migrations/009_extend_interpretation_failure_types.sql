-- Expand interpretation_failures.failure_type CHECK for curated failure taxonomy.
-- Adds: value_hidden_by_event, correction_partial
-- Keeps existing types from 003_create_interpretation_failures.sql

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
                'value_hidden_by_event'
            )
        );
