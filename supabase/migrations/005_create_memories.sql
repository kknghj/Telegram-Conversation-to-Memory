-- Approved memories (remote mirror of local JSON canonical source when STORAGE_BACKEND=supabase)

CREATE TABLE IF NOT EXISTS memories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source text NOT NULL DEFAULT 'telegram',
    telegram_user_id text,
    timestamp timestamptz,
    topic text,
    event_summary text,
    user_emotions jsonb NOT NULL DEFAULT '[]'::jsonb,
    emotion_evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
    people jsonb NOT NULL DEFAULT '[]'::jsonb,
    projects jsonb NOT NULL DEFAULT '[]'::jsonb,
    tags jsonb NOT NULL DEFAULT '[]'::jsonb,
    memory_candidate text,
    interpretation_risk text,
    unsupported_inferences jsonb NOT NULL DEFAULT '[]'::jsonb,
    needs_followup boolean,
    followup_question text,
    conversation jsonb NOT NULL DEFAULT '[]'::jsonb,
    raw_memory jsonb NOT NULL,
    approved boolean NOT NULL DEFAULT true,
    schema_version integer NOT NULL DEFAULT 2,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memories_timestamp ON memories (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_memories_topic ON memories (topic);
CREATE INDEX IF NOT EXISTS idx_memories_tags ON memories USING gin (tags);
CREATE INDEX IF NOT EXISTS idx_memories_people ON memories USING gin (people);
CREATE INDEX IF NOT EXISTS idx_memories_projects ON memories USING gin (projects);
CREATE INDEX IF NOT EXISTS idx_memories_telegram_user_id ON memories (telegram_user_id);
