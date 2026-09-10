-- Cluster roles that the databases' grants refer to.
--
-- `pg_dump` dumps grants but never the roles they name, so a restored tenant
-- database whose audit tables `GRANT SELECT ... TO acmis_auditor` fails on the
-- grant unless the role already exists. The tenant migrations create it too
-- (see `63b53e7141fc_audit_append_only`); this exists so a *restore* into a
-- fresh cluster works without having to run migrations first.
--
-- NOLOGIN and SELECT-only by construction: it is the role a regulator's
-- auditor is granted, and it must not be able to write to the trail it is
-- auditing.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'acmis_auditor') THEN
        CREATE ROLE acmis_auditor NOLOGIN;
    END IF;
END
$$;
