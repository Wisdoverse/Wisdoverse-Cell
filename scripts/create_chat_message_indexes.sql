-- Chat Messages Full-Text Search Index
-- Run this script after deploying to create the GIN index for full-text search
-- This index enables efficient Chinese text search using PostgreSQL's 'simple' configuration

-- Full-text search GIN index (for keyword search)
CREATE INDEX IF NOT EXISTS ix_chat_messages_content_gin
ON chat_messages USING gin(to_tsvector('simple', content));

-- Note: The following indexes are created automatically by SQLAlchemy:
-- - ix_chat_messages_chat_session (chat_id, session_id)
-- - ix_chat_messages_sent_at (sent_at)
-- - ix_chat_messages_extracted (extracted)
-- - unique constraint on message_id (for deduplication)

-- Verify indexes
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'chat_messages';
