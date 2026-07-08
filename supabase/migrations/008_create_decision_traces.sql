-- Decision traces: 후속 질문·프로젝트 태그 판단 과정의 관찰 가능성 로그.
-- Render 상시 운영 환경에서 "왜 질문이 안 나왔는가 / 왜 태그가 빠졌는가"를 사후 분석한다.

CREATE TABLE IF NOT EXISTS decision_traces (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id text,
    created_at timestamptz NOT NULL DEFAULT now(),

    source text NOT NULL DEFAULT 'telegram',
    environment text NOT NULL DEFAULT 'production',

    prompt_version text,
    model text,

    question_trace jsonb,
    project_trace jsonb,
    tag_trace jsonb,

    raw_input_preview text,
    error text
);

CREATE INDEX IF NOT EXISTS idx_decision_traces_memory_id
ON decision_traces(memory_id);

CREATE INDEX IF NOT EXISTS idx_decision_traces_created_at
ON decision_traces(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_decision_traces_question_reason
ON decision_traces ((question_trace->>'reason'));

CREATE INDEX IF NOT EXISTS idx_decision_traces_project_tag_written
ON decision_traces ((project_trace->>'tag_written'));
