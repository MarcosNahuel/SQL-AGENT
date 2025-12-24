-- =========================================================
-- SQL-AGENT Memory Tables Migration
-- Execute this in Supabase SQL Editor
-- =========================================================

-- 1. Agent Memory Table (Long-term memory store)
-- Used for storing user preferences, facts, and semantic memories
CREATE TABLE IF NOT EXISTS agent_memory (
    id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,
    key TEXT NOT NULL,
    value JSONB NOT NULL DEFAULT '{}',
    user_id TEXT,
    -- embedding vector(1536),  -- Uncomment if pgvector is enabled
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',

    -- Unique constraint per namespace/key/user
    UNIQUE(namespace, key, user_id)
);

-- To enable semantic search, first enable pgvector extension:
-- CREATE EXTENSION IF NOT EXISTS vector;
-- Then add the embedding column:
-- ALTER TABLE agent_memory ADD COLUMN embedding vector(1536);

-- Indexes for agent_memory
CREATE INDEX IF NOT EXISTS idx_agent_memory_namespace ON agent_memory(namespace);
CREATE INDEX IF NOT EXISTS idx_agent_memory_user ON agent_memory(user_id);
CREATE INDEX IF NOT EXISTS idx_agent_memory_expires ON agent_memory(expires_at) WHERE expires_at IS NOT NULL;

-- RLS Policies for agent_memory
ALTER TABLE agent_memory ENABLE ROW LEVEL SECURITY;

-- Allow service role full access
CREATE POLICY "Service role can do everything on agent_memory"
    ON agent_memory FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- 2. LangGraph Checkpoints Table
-- Used for persisting graph state between invocations
CREATE TABLE IF NOT EXISTS langgraph_checkpoints (
    id BIGSERIAL PRIMARY KEY,
    thread_id TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    checkpoint JSONB NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Unique constraint per thread/checkpoint
    UNIQUE(thread_id, checkpoint_id)
);

-- Indexes for langgraph_checkpoints
CREATE INDEX IF NOT EXISTS idx_lg_checkpoints_thread ON langgraph_checkpoints(thread_id);
CREATE INDEX IF NOT EXISTS idx_lg_checkpoints_created ON langgraph_checkpoints(created_at DESC);

-- RLS for langgraph_checkpoints
ALTER TABLE langgraph_checkpoints ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role can do everything on checkpoints"
    ON langgraph_checkpoints FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- 3. Conversation History Table
-- Used for storing chat history per session
CREATE TABLE IF NOT EXISTS conversation_history (
    id BIGSERIAL PRIMARY KEY,
    thread_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(thread_id, message_id)
);

-- Indexes for conversation_history
CREATE INDEX IF NOT EXISTS idx_conv_history_thread ON conversation_history(thread_id);
CREATE INDEX IF NOT EXISTS idx_conv_history_created ON conversation_history(created_at DESC);

-- RLS for conversation_history
ALTER TABLE conversation_history ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role can do everything on history"
    ON conversation_history FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- 4. Function for semantic search (requires pgvector extension)
-- Uncomment if you have pgvector enabled:
/*
CREATE OR REPLACE FUNCTION search_memory_semantic(
    query_embedding vector(1536),
    match_namespace TEXT DEFAULT NULL,
    match_user_id TEXT DEFAULT NULL,
    match_count INT DEFAULT 5,
    match_threshold FLOAT DEFAULT 0.7
)
RETURNS TABLE (
    id TEXT,
    namespace TEXT,
    key TEXT,
    value JSONB,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        m.id,
        m.namespace,
        m.key,
        m.value,
        1 - (m.embedding <=> query_embedding) AS similarity
    FROM agent_memory m
    WHERE
        (match_namespace IS NULL OR m.namespace = match_namespace)
        AND (match_user_id IS NULL OR m.user_id = match_user_id)
        AND m.embedding IS NOT NULL
        AND 1 - (m.embedding <=> query_embedding) > match_threshold
    ORDER BY m.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
*/

-- 5. Cleanup function for expired memories
CREATE OR REPLACE FUNCTION cleanup_expired_memories()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM agent_memory
    WHERE expires_at IS NOT NULL AND expires_at < NOW();

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$;

-- 6. Trigger to auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_agent_memory_updated_at
    BEFORE UPDATE ON agent_memory
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =========================================================
-- Grant permissions to anon and authenticated roles if needed
-- =========================================================
-- GRANT SELECT, INSERT, UPDATE, DELETE ON agent_memory TO service_role;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON langgraph_checkpoints TO service_role;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON conversation_history TO service_role;

-- =========================================================
-- Verify installation
-- =========================================================
SELECT 'agent_memory' AS table_name, COUNT(*) AS rows FROM agent_memory
UNION ALL
SELECT 'langgraph_checkpoints', COUNT(*) FROM langgraph_checkpoints
UNION ALL
SELECT 'conversation_history', COUNT(*) FROM conversation_history;
