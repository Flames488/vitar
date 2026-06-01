-- Vitar v5 PostgreSQL initialization
-- Enable extensions needed for production

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";    -- For fast text search on names/emails
CREATE EXTENSION IF NOT EXISTS "btree_gin";  -- For JSONB GIN indexes

-- Set timezone
SET timezone = 'UTC';

-- Performance settings (applied at session level for migrations)
SET lock_timeout = '10s';
SET statement_timeout = '30s';
