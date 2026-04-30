-- =============================================================================
-- Wisdoverse Cell - Database Initialization
-- =============================================================================
-- This script runs on first container startup when postgres_data volume is empty.
-- =============================================================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For fuzzy text search

-- Create schema if not exists
CREATE SCHEMA IF NOT EXISTS projectcell;

-- Grant permissions
GRANT ALL PRIVILEGES ON SCHEMA projectcell TO projectcell;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA projectcell TO projectcell;
ALTER DEFAULT PRIVILEGES IN SCHEMA projectcell GRANT ALL ON TABLES TO projectcell;

-- Log initialization
DO $$
BEGIN
    RAISE NOTICE 'Wisdoverse Cell database initialized at %', NOW();
END $$;
