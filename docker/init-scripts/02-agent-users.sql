-- =============================================================================
-- Per-agent PostgreSQL users for least-privilege access
-- =============================================================================
-- Runs on first DB initialization only (docker-entrypoint-initdb.d).
-- Idempotent: safe to re-run manually via psql.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Create agent-specific roles
--    Passwords sourced from env vars at deploy time; defaults for local dev.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    -- Chat Agent: conversation histories, card operations, daily progress
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'chat_agent') THEN
        CREATE ROLE chat_agent WITH LOGIN PASSWORD 'chat_agent_dev';
    END IF;

    -- PJM Agent: alert logs, config cache, decomposition records
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'pjm_agent') THEN
        CREATE ROLE pjm_agent WITH LOGIN PASSWORD 'pjm_agent_dev';
    END IF;

    -- Sync Agent: mappings, subtask mappings, logs, locks
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sync_agent') THEN
        CREATE ROLE sync_agent WITH LOGIN PASSWORD 'sync_agent_dev';
    END IF;

    -- Analysis Agent: report logs
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analysis_agent') THEN
        CREATE ROLE analysis_agent WITH LOGIN PASSWORD 'analysis_agent_dev';
    END IF;

    -- QA Agent: acceptance runs, results
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'qa_agent') THEN
        CREATE ROLE qa_agent WITH LOGIN PASSWORD 'qa_agent_dev';
    END IF;

    -- Dev Agent: delivery tasks and workflow execution logs
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'dev_agent') THEN
        CREATE ROLE dev_agent WITH LOGIN PASSWORD 'dev_agent_dev';
    END IF;

    -- Evolution Agent: traces, skill configs, reflections, experiments, memory, patterns
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'evolution_agent') THEN
        CREATE ROLE evolution_agent WITH LOGIN PASSWORD 'evolution_agent_dev';
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- 2. Grant connect & schema usage
-- ---------------------------------------------------------------------------
GRANT CONNECT ON DATABASE projectcell TO chat_agent, pjm_agent, sync_agent, analysis_agent, qa_agent, dev_agent, evolution_agent;
GRANT USAGE ON SCHEMA public TO chat_agent, pjm_agent, sync_agent, analysis_agent, qa_agent, dev_agent, evolution_agent;

-- ---------------------------------------------------------------------------
-- 3. Table-level grants (tables created by Alembic / SQLAlchemy on first run)
--    These GRANT statements are deferred — they will fail silently if tables
--    don't exist yet.  Re-run this script (or the GRANT block) after the
--    first application startup that creates the tables.
-- ---------------------------------------------------------------------------

-- Chat Agent tables
DO $$
BEGIN
    -- Own tables: full CRUD
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
        chat_agent_conversation_histories,
        chat_agent_card_operations,
        chat_agent_daily_progress
    TO chat_agent;
EXCEPTION WHEN undefined_table THEN
    RAISE NOTICE 'chat_agent tables do not exist yet — skipping grants';
END
$$;

-- PJM Agent tables
DO $$
BEGIN
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
        pjm_agent_alert_logs,
        pjm_agent_config_cache,
        pjm_agent_decomposition_records
    TO pjm_agent;
EXCEPTION WHEN undefined_table THEN
    RAISE NOTICE 'pjm_agent tables do not exist yet — skipping grants';
END
$$;

-- Sync Agent tables
DO $$
BEGIN
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
        sync_agent_mappings,
        sync_agent_subtask_mappings,
        sync_agent_logs,
        sync_agent_locks
    TO sync_agent;
EXCEPTION WHEN undefined_table THEN
    RAISE NOTICE 'sync_agent tables do not exist yet — skipping grants';
END
$$;

-- Analysis Agent tables
DO $$
BEGIN
    -- Own tables: full CRUD
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
        analysis_agent_report_logs
    TO analysis_agent;

    -- Cross-agent read access for analysis
    GRANT SELECT ON TABLE
        chat_agent_conversation_histories,
        chat_agent_daily_progress,
        pjm_agent_alert_logs,
        pjm_agent_decomposition_records,
        sync_agent_mappings,
        sync_agent_subtask_mappings
    TO analysis_agent;
EXCEPTION WHEN undefined_table THEN
    RAISE NOTICE 'analysis/cross-agent tables do not exist yet — skipping grants';
END
$$;

-- ---------------------------------------------------------------------------
-- 4. Sequence usage (auto-increment IDs)
-- ---------------------------------------------------------------------------
-- QA Agent tables
DO $$
BEGIN
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
        qa_acceptance_runs,
        qa_acceptance_results
    TO qa_agent;
EXCEPTION WHEN undefined_table THEN
    RAISE NOTICE 'qa_agent tables do not exist yet — skipping grants';
END
$$;

-- Dev Agent tables
DO $$
BEGIN
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
        dev_agent_tasks,
        dev_agent_workflow_logs
    TO dev_agent;
EXCEPTION WHEN undefined_table THEN
    RAISE NOTICE 'dev_agent tables do not exist yet — skipping grants';
END
$$;

-- Evolution Agent tables
DO $$
BEGIN
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
        evolution_traces,
        evolution_skill_configs,
        evolution_reflections,
        evolution_experiments,
        evolution_memory,
        evolution_collaboration_patterns
    TO evolution_agent;

    -- Evolution Agent also needs read access to all agent tables for global analysis
    GRANT SELECT ON TABLE
        chat_agent_conversation_histories,
        chat_agent_daily_progress,
        pjm_agent_alert_logs,
        pjm_agent_decomposition_records,
        sync_agent_mappings,
        sync_agent_logs,
        qa_acceptance_runs,
        qa_acceptance_results,
        dev_agent_tasks,
        dev_agent_workflow_logs
    TO evolution_agent;
EXCEPTION WHEN undefined_table THEN
    RAISE NOTICE 'evolution/cross-agent tables do not exist yet — skipping grants';
END
$$;

GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO chat_agent, pjm_agent, sync_agent, analysis_agent, qa_agent, dev_agent, evolution_agent;

-- Default privileges so future sequences are also accessible
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO chat_agent, pjm_agent, sync_agent, analysis_agent, qa_agent, dev_agent, evolution_agent;

-- ---------------------------------------------------------------------------
-- Done
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    RAISE NOTICE 'Per-agent DB users initialized at %', NOW();
END
$$;
