-- In-progress and cancelled drafts for Render-safe recovery.

CREATE TABLE IF NOT EXISTS drafts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_user_id text NOT NULL,
    status text NOT NULL CHECK (status IN ('active', 'cancelled', 'saved')),
    raw_text jsonb NOT NULL DEFAULT '{}'::jsonb,
    summary_json jsonb,
    cancellation_reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_drafts_telegram_user_status
    ON drafts (telegram_user_id, status);

CREATE INDEX IF NOT EXISTS idx_drafts_updated_at
    ON drafts (updated_at);

CREATE INDEX IF NOT EXISTS idx_drafts_status_updated_at
    ON drafts (status, updated_at);
