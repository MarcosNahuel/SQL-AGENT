-- Migration: 001_langgraph_tables.sql
-- Description: Tables for LangGraph checkpoints, writes, and agent memory
-- Created: 2024-12-21

-- ============================================
-- LANGGRAPH CHECKPOINTS TABLE
-- Stores graph state snapshots for persistence
-- ============================================
CREATE TABLE IF NOT EXISTS langgraph_checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint JSONB NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

-- Index for faster lookups by thread
CREATE INDEX IF NOT EXISTS idx_checkpoints_thread
ON langgraph_checkpoints(thread_id, created_at DESC);

-- ============================================
-- LANGGRAPH WRITES TABLE
-- Stores intermediate writes between checkpoints
-- ============================================
CREATE TABLE IF NOT EXISTS langgraph_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    value JSONB,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

-- Index for checkpoint lookups
CREATE INDEX IF NOT EXISTS idx_writes_checkpoint
ON langgraph_writes(thread_id, checkpoint_ns, checkpoint_id);

-- ============================================
-- AGENT MEMORY TABLE
-- Long-term memory storage across threads
-- ============================================
CREATE TABLE IF NOT EXISTS agent_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT,
    namespace TEXT NOT NULL,
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE,
    UNIQUE(user_id, namespace, key)
);

-- Indexes for memory lookups
CREATE INDEX IF NOT EXISTS idx_memory_user_namespace
ON agent_memory(user_id, namespace);

CREATE INDEX IF NOT EXISTS idx_memory_expires
ON agent_memory(expires_at)
WHERE expires_at IS NOT NULL;

-- ============================================
-- CHAT HISTORY TABLE
-- Stores conversation history per thread
-- ============================================
CREATE TABLE IF NOT EXISTS chat_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id TEXT NOT NULL,
    user_id TEXT,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for conversation retrieval
CREATE INDEX IF NOT EXISTS idx_chat_thread
ON chat_history(thread_id, created_at ASC);

-- ============================================
-- TRIGGER: Update updated_at on agent_memory
-- ============================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_agent_memory_updated_at ON agent_memory;
CREATE TRIGGER update_agent_memory_updated_at
    BEFORE UPDATE ON agent_memory
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- COMMENTS
-- ============================================
COMMENT ON TABLE langgraph_checkpoints IS 'LangGraph state checkpoints for graph persistence';
COMMENT ON TABLE langgraph_writes IS 'Intermediate writes between LangGraph checkpoints';
COMMENT ON TABLE agent_memory IS 'Long-term agent memory across conversation threads';
COMMENT ON TABLE chat_history IS 'Conversation history per thread';
