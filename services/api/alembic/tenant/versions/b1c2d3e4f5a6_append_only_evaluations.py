"""Make evaluation responses and attendance registers tamper-evident.

`evaluation_response` claims anonymity in its docstring. This makes the
database enforce it: with UPDATE discarded, nobody can ever back-fill an
identifying column onto an existing response, and with DELETE discarded,
nobody can remove the comment they did not like. The claim stops depending on
every future writer of the service layer remembering it.

`session_attendance` is not append-only, and deliberately so — a register is
corrected all the time, a student marked absent turns out to have been in the
room, and a system that cannot fix that gets a paper register kept beside it.
What it gets instead is a trigger refusing a change to a *closed* register
except through the dispute fields, which is the distinction that matters: a
correction with a trail is fine, a silent one after the fact is not.

Revision ID: b1c2d3e4f5a6
Revises: 246c13e084f8
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "246c13e084f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPEND_ONLY = ("evaluation_response",)


def upgrade() -> None:
    for table in APPEND_ONLY:
        op.execute(f'DROP RULE IF EXISTS "{table}_no_update" ON "{table}"')
        op.execute(f'DROP RULE IF EXISTS "{table}_no_delete" ON "{table}"')
        op.execute(f'CREATE RULE "{table}_no_update" AS ON UPDATE TO "{table}" DO INSTEAD NOTHING')
        op.execute(f'CREATE RULE "{table}_no_delete" AS ON DELETE TO "{table}" DO INSTEAD NOTHING')
        op.execute(f'GRANT SELECT ON "{table}" TO acmis_auditor')

    # A closed register may still be corrected — but only through the dispute
    # fields, and only with a resolver recorded. Everything else about the row
    # is frozen, so "the mark was changed after the register closed" is always
    # accompanied by who changed it and why.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION acmis_guard_closed_register()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            closed_at timestamptz;
        BEGIN
            SELECT cs.register_closed_at INTO closed_at
            FROM class_session cs WHERE cs.id = NEW.session_id;

            IF closed_at IS NULL THEN
                RETURN NEW;                     -- register still open
            END IF;

            IF NEW.status IS DISTINCT FROM OLD.status
               AND (NEW.dispute_note IS NULL OR NEW.resolved_by_id IS NULL) THEN
                RAISE EXCEPTION
                    'attendance on a closed register may only be corrected through a '
                    'recorded dispute (session %, student %)',
                    NEW.session_id, NEW.student_id
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_closed_register ON session_attendance")
    op.execute(
        """
        CREATE TRIGGER trg_closed_register
        BEFORE UPDATE ON session_attendance
        FOR EACH ROW EXECUTE FUNCTION acmis_guard_closed_register()
        """
    )
    op.execute("GRANT SELECT ON session_attendance TO acmis_auditor")
    op.execute("GRANT SELECT ON class_session TO acmis_auditor")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_closed_register ON session_attendance")
    op.execute("DROP FUNCTION IF EXISTS acmis_guard_closed_register()")
    for table in APPEND_ONLY:
        op.execute(f'DROP RULE IF EXISTS "{table}_no_update" ON "{table}"')
        op.execute(f'DROP RULE IF EXISTS "{table}_no_delete" ON "{table}"')
