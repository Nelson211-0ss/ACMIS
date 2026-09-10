"""Make the audit tables append-only, in the database.

Everything else in this system protects data. This protects the record *of*
the protection, and it is the one guarantee that cannot be left to application
discipline: a trail the application can rewrite is worth nothing in the
dispute it exists to settle. Comments in `core/audit.py` promise append-only;
this is where the promise is actually kept.

Implemented with `CREATE RULE ... DO INSTEAD NOTHING` rather than a trigger
that raises. A raising trigger turns a stray UPDATE into a failed request,
which sounds stricter but is worse in practice: an accidental bulk UPDATE
during an incident would take the API down. A rule silently discards the
write, so the trail is unchanged and the caller learns nothing about the
attempt — and the attempt itself is visible in the Postgres log.

`REVOKE` alone would not do: the application role owns these tables and a
table owner's privileges cannot be revoked from itself in a way that survives.
A rule applies to everyone, owner included.

Revision ID: 63b53e7141fc
Revises: 63b53e7141fb
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "63b53e7141fc"
down_revision: str | None = "63b53e7141fb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Tables that may only ever be inserted into.
APPEND_ONLY = (
    "audit_event",
    "access_log",
    "abac_policy_change",
    "login_attempt",
    "ledger_entry",
    "webhook_delivery",
    "integration_log",
    "platform_event",
)


def upgrade() -> None:
    for table in APPEND_ONLY:
        op.execute(f'CREATE RULE "{table}_no_update" AS ON UPDATE TO "{table}" DO INSTEAD NOTHING')
        op.execute(f'CREATE RULE "{table}_no_delete" AS ON DELETE TO "{table}" DO INSTEAD NOTHING')

    # Retention still has to be possible — a ten-year audit retention is a
    # policy, not "forever" — so purging goes through a function that drops the
    # rules, deletes by date, and restores them. Owner-only, and every call is
    # recorded in the platform trail by the job that invokes it.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION acmis_purge_audit(
            p_table text, p_before timestamptz
        ) RETURNS bigint
        LANGUAGE plpgsql
        SECURITY DEFINER
        AS $$
        DECLARE
            affected bigint;
        BEGIN
            IF p_table NOT IN (
                'audit_event', 'access_log', 'login_attempt',
                'webhook_delivery', 'integration_log', 'platform_event'
            ) THEN
                RAISE EXCEPTION 'acmis_purge_audit: % is not a purgeable table', p_table;
            END IF;
            -- Never the financial ledger and never the policy history: those
            -- have no retention limit, because a fee dispute and "what were
            -- the rules in March 2027" can both surface long after ten years.

            EXECUTE format('DROP RULE IF EXISTS %I ON %I', p_table || '_no_delete', p_table);
            EXECUTE format(
                'DELETE FROM %I WHERE occurred_at < $1', p_table
            ) USING p_before;
            GET DIAGNOSTICS affected = ROW_COUNT;
            EXECUTE format(
                'CREATE RULE %I AS ON DELETE TO %I DO INSTEAD NOTHING',
                p_table || '_no_delete', p_table
            );
            RETURN affected;
        END;
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION acmis_purge_audit(text, timestamptz) FROM PUBLIC")

    # A read-only role for auditors and the reporting replica. Granted SELECT
    # on the trail and nothing else, so an external auditor can be given real
    # access without being able to touch a student record.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'acmis_auditor') THEN
                CREATE ROLE acmis_auditor NOLOGIN;
            END IF;
        END $$;
        """
    )
    for table in APPEND_ONLY:
        op.execute(f'GRANT SELECT ON "{table}" TO acmis_auditor')


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS acmis_purge_audit(text, timestamptz)")
    for table in APPEND_ONLY:
        op.execute(f'DROP RULE IF EXISTS "{table}_no_update" ON "{table}"')
        op.execute(f'DROP RULE IF EXISTS "{table}_no_delete" ON "{table}"')
