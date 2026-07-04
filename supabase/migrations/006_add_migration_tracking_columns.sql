-- Migration tracking columns for local JSON → Supabase import

ALTER TABLE memories
    ADD COLUMN IF NOT EXISTS source_hash text,
    ADD COLUMN IF NOT EXISTS source_file text,
    ADD COLUMN IF NOT EXISTS migrated_at timestamptz DEFAULT now();

CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_source_hash
    ON memories (source_hash);

CREATE INDEX IF NOT EXISTS idx_memories_source_file ON memories (source_file);
