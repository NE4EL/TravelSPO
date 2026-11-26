import os

import sqlalchemy as sa
from fastapi import Request

url = os.environ.get("DATABASE_URL", "sqlite:///travel.db")
engine = sa.create_engine(url)


def enable_foreign_keys(connection, _):
    connection.execute("PRAGMA foreign_keys=ON")


if engine.dialect.name == "sqlite":
    sa.event.listen(engine, "connect", enable_foreign_keys)


def transaction(request: Request):
    with engine.begin() as conn:
        if conn.dialect.name == "sqlite":
            conn.exec_driver_sql(
                "BEGIN" if request.method == "GET" else "BEGIN IMMEDIATE"
            )
        yield conn


metadata = sa.MetaData()


def primary_key():
    return sa.Column("id", sa.Integer, primary_key=True)


def reference(name, target, *, nullable=False, ondelete="CASCADE"):
    return sa.Column(
        name,
        sa.Integer,
        sa.ForeignKey(target, ondelete=ondelete),
        nullable=nullable,
        index=True,
    )


def created_at():
    return sa.Column(
        "created_at", sa.DateTime, nullable=False, server_default=sa.func.now()
    )


users = sa.Table(
    "users",
    metadata,
    primary_key(),
    sa.Column("email", sa.String(255), nullable=False, unique=True),
    sa.Column("password_hash", sa.String(255), nullable=False),
    created_at(),
)

sessions = sa.Table(
    "sessions",
    metadata,
    sa.Column("digest", sa.String(64), primary_key=True),
    reference("user_id", "users.id"),
    sa.Column("expires_at", sa.DateTime, nullable=False),
)

trips = sa.Table(
    "trips",
    metadata,
    primary_key(),
    reference("user_id", "users.id"),
    sa.Column("title", sa.String(120), nullable=False),
    sa.Column("destination", sa.String(120), nullable=False),
    sa.Column("start_date", sa.Date, nullable=False),
    sa.Column("end_date", sa.Date, nullable=False),
    sa.Column("budget_limit", sa.Numeric(12, 2), nullable=False),
    created_at(),
    sa.CheckConstraint("end_date >= start_date"),
    sa.CheckConstraint("budget_limit >= 0"),
)

activities = sa.Table(
    "activities",
    metadata,
    primary_key(),
    reference("trip_id", "trips.id"),
    sa.Column("title", sa.String(120), nullable=False),
    sa.Column("activity_date", sa.Date, nullable=False),
    sa.Column("starts_at", sa.Time),
    sa.Column("ends_at", sa.Time),
    sa.Column("description", sa.Text),
    sa.CheckConstraint(
        "ends_at IS NULL OR (starts_at IS NOT NULL AND ends_at >= starts_at)"
    ),
)
sa.Index("uq_activities_id_trip_id", activities.c.id, activities.c.trip_id, unique=True)

expenses = sa.Table(
    "expenses",
    metadata,
    primary_key(),
    reference("trip_id", "trips.id"),
    reference("activity_id", "activities.id", nullable=True, ondelete="SET NULL"),
    sa.Column("title", sa.String(120), nullable=False),
    sa.Column("amount", sa.Numeric(12, 2), nullable=False),
    created_at(),
    sa.CheckConstraint("amount > 0"),
    # Keep the simple FK for SET NULL; check the pair after its delete action.
    sa.ForeignKeyConstraint(
        ["activity_id", "trip_id"],
        ["activities.id", "activities.trip_id"],
        name="fk_expenses_activity_trip",
        deferrable=True,
        initially="DEFERRED",
    ),
)

packing_items = sa.Table(
    "packing_items",
    metadata,
    primary_key(),
    reference("trip_id", "trips.id"),
    sa.Column("name", sa.String(120), nullable=False),
    sa.Column("is_packed", sa.Boolean, nullable=False),
    sa.Column("sort_order", sa.Integer, nullable=False),
)
