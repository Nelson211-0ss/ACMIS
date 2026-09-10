"""Make a cast ballot unalterable in the database.

The policy bundle refuses to update or delete a ballot, and the service never
tries. This is the layer below both: with `UPDATE` and `DELETE` discarded by
Postgres itself, a ballot cannot be changed by anyone holding a connection —
a platform administrator, a restored backup being edited, or a future
maintainer who adds an endpoint without reading the policy.

An election is the one process in this system where the people running it are
the most likely source of a challenge, so "the application prevents it" is not
a strong enough answer. This makes the count reproducible from data that
cannot have moved.

`election_voter_roll` is deliberately *not* append-only: it is stamped when a
voter votes, and it has to be, so the same voter cannot vote twice.

Revision ID: c1d2e3f4a5b6
Revises: 7f31dc4e024f
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "7f31dc4e024f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('DROP RULE IF EXISTS "election_ballot_no_update" ON "election_ballot"')
    op.execute('DROP RULE IF EXISTS "election_ballot_no_delete" ON "election_ballot"')
    op.execute(
        'CREATE RULE "election_ballot_no_update" AS ON UPDATE TO "election_ballot" '
        "DO INSTEAD NOTHING"
    )
    op.execute(
        'CREATE RULE "election_ballot_no_delete" AS ON DELETE TO "election_ballot" '
        "DO INSTEAD NOTHING"
    )
    # The auditor reads the count and the roll, and cannot read a ballot —
    # there is no grant for that anywhere, by design.
    op.execute("GRANT SELECT ON election_voter_roll TO acmis_auditor")
    op.execute("GRANT SELECT ON election_result TO acmis_auditor")
    op.execute("GRANT SELECT ON election_candidate TO acmis_auditor")


def downgrade() -> None:
    op.execute('DROP RULE IF EXISTS "election_ballot_no_update" ON "election_ballot"')
    op.execute('DROP RULE IF EXISTS "election_ballot_no_delete" ON "election_ballot"')
