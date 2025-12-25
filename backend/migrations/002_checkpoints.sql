-- Migration: 002_checkpoints.sql
-- Description: Create tables for LangGraph checkpoint persistence

-- Checkpoints table - stores graph state snapshots
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_thread ON checkpoints (thread_id, checkpoint_ns);
CREATE INDEX IF NOT EXISTS idx_checkpoints_created ON checkpoints (created_at);

-- Checkpoint writes table
CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    blob BYTEA,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

CREATE INDEX IF NOT EXISTS idx_checkpoint_writes_thread ON checkpoint_writes (thread_id, checkpoint_ns, checkpoint_id);

-- Checkpoint blobs table
CREATE TABLE IF NOT EXISTS checkpoint_blobs (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL,
    version TEXT NOT NULL,
    type TEXT NOT NULL,
    blob BYTEA,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);

CREATE INDEX IF NOT EXISTS idx_checkpoint_blobs_thread ON checkpoint_blobs (thread_id, checkpoint_ns);

-- Agent memory table - long-term preferences
CREATE TABLE IF NOT EXISTS agent_memory (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    thread_id TEXT,
    memory_type TEXT NOT NULL,
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    confidence FLOAT DEFAULT 1.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    UNIQUE (user_id, memory_type, key)
);

CREATE INDEX IF NOT EXISTS idx_agent_memory_user ON agent_memory (user_id, memory_type);
CREATE INDEX IF NOT EXISTS idx_agent_memory_thread ON agent_memory (thread_id) WHERE thread_id IS NOT NULL;

-- Chat messages table - conversation history
CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    thread_id TEXT NOT NULL,
    user_id TEXT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_thread ON chat_messages (thread_id, created_at);

-- Auto-update trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for agent_memory
DROP TRIGGER IF EXISTS update_agent_memory_updated_at ON agent_memory;
CREATE TRIGGER update_agent_memory_updated_at
    BEFORE UPDATE ON agent_memory
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
