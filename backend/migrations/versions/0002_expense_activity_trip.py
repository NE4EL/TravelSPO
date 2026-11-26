"""Require an expense and its activity to belong to the same trip.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Do not silently rewrite expenses imported before this constraint existed.
    if not op.get_context().as_sql:
        invalid = op.get_bind().execute(
            sa.text(
                "SELECT e.id FROM expenses e LEFT JOIN activities a ON a.id = e.activity_id "
                "WHERE e.activity_id IS NOT NULL "
                "AND (a.id IS NULL OR a.trip_id <> e.trip_id) LIMIT 1"
            )
        ).scalar()
        if invalid is not None:
            raise RuntimeError(
                f"Expense {invalid} references an activity outside its trip. "
                "Correct its activity_id before applying migration 0002."
            )

    op.create_index("uq_activities_id_trip_id", "activities", ["id", "trip_id"], unique=True)
    with op.batch_alter_table("expenses") as batch:
        batch.create_foreign_key(
            "fk_expenses_activity_trip",
            "activities",
            ["activity_id", "trip_id"],
            ["id", "trip_id"],
            deferrable=True,
            initially="DEFERRED",
        )


def downgrade() -> None:
    with op.batch_alter_table("expenses") as batch:
        batch.drop_constraint("fk_expenses_activity_trip", type_="foreignkey")
    op.drop_index("uq_activities_id_trip_id", table_name="activities")
