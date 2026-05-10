-- =============================================================================
-- Wisdoverse Cell - Database Initialization
-- =============================================================================
-- This script runs on first container startup when postgres_data volume is empty.
-- =============================================================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For fuzzy text search

-- Create schema if not exists
CREATE SCHEMA IF NOT EXISTS wisdoverse-cell;

-- Grant permissions
GRANT ALL PRIVILEGES ON SCHEMA wisdoverse-cell TO wisdoverse-cell;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA wisdoverse-cell TO wisdoverse-cell;
ALTER DEFAULT PRIVILEGES IN SCHEMA wisdoverse-cell GRANT ALL ON TABLES TO wisdoverse-cell;

-- Log initialization
DO $$
BEGIN
    RAISE NOTICE 'Wisdoverse Cell database initialized at %', NOW();
END $$;
