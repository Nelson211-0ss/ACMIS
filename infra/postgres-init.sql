-- Runs once, on first cluster start.
--
-- Extensions are created in `template1` so that every tenant database created
-- later by `CREATE DATABASE ... TEMPLATE template0` — and every one created
-- from the default template — has them without provisioning having to
-- remember. Forgetting `pg_trgm` in one tenant database means student search
-- silently falls back to a sequential scan there and nowhere else.
\c template1
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gin";
CREATE EXTENSION IF NOT EXISTS "unaccent";

\c acmis_control
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
