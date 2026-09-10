"""Extend the append-only guard to the learning and interop tables.

A separate migration rather than an edit to `63b53e7141fc`, because that one
has already been applied. Editing an applied migration means the databases
that ran the old version and the ones that will run the new one diverge
silently, and with a database per tenant that divergence is invisible until
one university behaves differently from the rest.

Why these tables specifically:

* `material_view` — engagement data about identified students. A corrected
  view count and a covered track are indistinguishable, and the pastoral value
  of the data depends on it being what actually happened.
* `lti_score` — what an external tool reported. The whole reason the sequence
  is kept is to settle "we sent 85" against "you recorded 40"; a mutable log
  settles nothing.
* `xapi_statement` — behavioural statements, same reasoning as material views.

Revision ID: f1a2b3c4d5e6
Revises: e88eecdb22aa
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "e88eecdb22aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPEND_ONLY = ("material_view", "lti_score", "xapi_statement")


def upgrade() -> None:
    for table in APPEND_ONLY:
        # `IF EXISTS` on the drop and a guarded create, so this is re-runnable
        # against a tenant database that a previous partial fan-out already
        # touched.
        op.execute(f'DROP RULE IF EXISTS "{table}_no_update" ON "{table}"')
        op.execute(f'DROP RULE IF EXISTS "{table}_no_delete" ON "{table}"')
        op.execute(f'CREATE RULE "{table}_no_update" AS ON UPDATE TO "{table}" DO INSTEAD NOTHING')
        op.execute(f'CREATE RULE "{table}_no_delete" AS ON DELETE TO "{table}" DO INSTEAD NOTHING')
        op.execute(f'GRANT SELECT ON "{table}" TO acmis_auditor')

    # `material_view` is aggregated per student per material and therefore
    # needs to be *updated* as a student re-opens something — which the rule
    # above forbids. The upsert path goes through this function instead, so
    # the only mutation possible is the one the domain intends: monotonically
    # increasing counters. A count that can only go up cannot be used to hide
    # that a student did look at something.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION acmis_touch_material_view(
            p_material_id uuid,
            p_student_id uuid,
            p_seconds integer,
            p_downloaded boolean,
            p_completion integer
        ) RETURNS uuid
        LANGUAGE plpgsql
        SECURITY DEFINER
        AS $$
        DECLARE
            existing_id uuid;
        BEGIN
            SELECT id INTO existing_id
            FROM material_view
            WHERE material_id = p_material_id AND student_id = p_student_id;

            IF existing_id IS NULL THEN
                INSERT INTO material_view (
                    id, material_id, student_id, first_viewed_at, last_viewed_at,
                    view_count, total_seconds, downloaded, completion_percent
                ) VALUES (
                    gen_random_uuid(), p_material_id, p_student_id, now(), now(),
                    1, GREATEST(p_seconds, 0), p_downloaded, p_completion
                ) RETURNING id INTO existing_id;
                RETURN existing_id;
            END IF;

            -- Counters only ever increase; `downloaded` only ever becomes true.
            -- The rule blocks a plain UPDATE, so this is the single path, and
            -- it cannot express "reduce" or "unset".
            EXECUTE '
                UPDATE material_view SET
                    last_viewed_at = now(),
                    view_count = view_count + 1,
                    total_seconds = total_seconds + GREATEST($3, 0),
                    downloaded = downloaded OR $4,
                    completion_percent = GREATEST(COALESCE(completion_percent, 0), COALESCE($5, 0))
                WHERE id = $1'
              USING existing_id, p_material_id, p_seconds, p_downloaded, p_completion;
            RETURN existing_id;
        END $$;
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION acmis_touch_material_view("
        "uuid, uuid, integer, boolean, integer) FROM PUBLIC"
    )


def downgrade() -> None:
    op.execute(
        "DROP FUNCTION IF EXISTS acmis_touch_material_view(uuid, uuid, integer, boolean, integer)"
    )
    for table in APPEND_ONLY:
        op.execute(f'DROP RULE IF EXISTS "{table}_no_update" ON "{table}"')
        op.execute(f'DROP RULE IF EXISTS "{table}_no_delete" ON "{table}"')
