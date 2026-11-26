from os import environ
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from app import db
from app.main import app
from fastapi.testclient import TestClient

CREDS = {"email": "guest@example.com", "password": "test-pass-123"}
TRIP = {
    "title": "Выходные",
    "destination": "Казань",
    "start_date": "2026-06-12",
    "end_date": "2026-06-14",
    "budget_limit": "1000.00",
}
ACTIVITY = {
    "title": "Экскурсия",
    "activity_date": "2026-06-13",
    "starts_at": "10:00",
    "ends_at": "12:00",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = sa.create_engine(
        environ.get("TEST_DATABASE_URL")
        or sa.URL.create("sqlite", database=str(tmp_path / "travel.db"))
    )
    if engine.dialect.name == "sqlite":
        sa.event.listen(engine, "connect", db.enable_foreign_keys)
    monkeypatch.setattr(db, "engine", engine)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    with TestClient(app) as client:
        yield client
    command.downgrade(config, "base")
    engine.dispose()


def create(client, url, values):
    response = client.post(url, json=values)
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
def trip(client):
    create(client, "/api/auth/register", CREDS)
    return "/api/trips/" + str(create(client, "/api/trips", TRIP))


def test_auth(client):
    assert client.get("/api/trips").status_code == 401
    create(client, "/api/auth/register", CREDS)
    assert client.post("/api/auth/register", json=CREDS).status_code == 409
    token = client.cookies.get("session")
    assert client.get("/api/auth/me").json()["email"] == CREDS["email"]
    assert client.post("/api/auth/logout").status_code == 204
    assert (
        client.get("/api/auth/me", headers={"Cookie": "session=" + token}).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login", json={**CREDS, "password": "bad-pass"}
        ).status_code
        == 401
    )
    assert client.post("/api/auth/login", json=CREDS).status_code == 200


def test_trip_validation_and_edit(client, trip):
    assert client.post("/api/trips", json={**TRIP, "title": "  "}).status_code == 422
    assert client.put(trip, json={**TRIP, "end_date": "2026-06-10"}).status_code == 422
    assert client.put(trip, json={**TRIP, "budget_limit": "-1"}).status_code == 422
    assert client.put(trip, json={**TRIP, "title": "Лето"}).status_code == 204
    assert client.get("/api/trips").json()[0]["title"] == "Лето"


def test_schedule(client, trip):
    url = trip + "/activities"
    assert client.post(url, json={**ACTIVITY, "ends_at": "08:00"}).status_code == 422
    assert (
        client.post(url, json={**ACTIVITY, "activity_date": "2026-06-15"}).status_code
        == 422
    )
    first = create(client, url, ACTIVITY)
    second = create(client, url, {**ACTIVITY, "starts_at": "09:00"})
    assert [a["id"] for a in client.get(trip).json()["activities"]] == [second, first]
    assert (
        client.put(trip, json={**TRIP, "start_date": "2026-06-14"}).status_code == 422
    )
    assert (
        client.put(
            f"{url}/{first}", json={**ACTIVITY, "activity_date": "2026-06-14"}
        ).status_code
        == 200
    )
    assert client.get(trip).json()["activities"][1]["activity_date"] == "2026-06-14"


def test_budget_and_unlink(client, trip):
    activity = create(client, trip + "/activities", ACTIVITY)
    url = trip + "/expenses"
    expense = {"title": "Билет", "amount": "850.35", "activity_id": activity}
    first = create(client, url, expense)
    create(client, url, {"title": "Обед", "amount": "249.90"})
    assert client.get(trip).json()["remaining"] == "-100.25"
    assert client.delete(f"{trip}/activities/{activity}").status_code == 204
    view = client.get(trip).json()
    assert view["expenses"][0]["activity_id"] is None
    assert view["total"] == "1100.25"
    assert (
        client.put(
            f"{url}/{first}", json={"title": "Билет", "amount": "800.10"}
        ).status_code
        == 200
    )
    assert client.get(trip).json()["total"] == "1050.00"
    assert client.delete(f"{url}/{first}").status_code == 204
    assert client.get(trip).json()["remaining"] == "750.10"


@pytest.mark.parametrize("amount", ["0", "-1", "1.001", "10000000000"])
def test_invalid_amount(client, trip, amount):
    assert (
        client.post(
            trip + "/expenses", json={"title": "Обед", "amount": amount}
        ).status_code
        == 422
    )


def test_items_and_cascade(client, trip):
    item = create(client, trip + "/items", {"name": "Паспорт"})
    for packed in (True, False):
        assert (
            client.put(
                f"{trip}/items/{item}", json={"name": "Паспорт", "is_packed": packed}
            ).status_code
            == 200
        )
        assert client.get(trip).json()["packing_items"][0]["is_packed"] is packed
    activity = create(client, trip + "/activities", ACTIVITY)
    create(
        client,
        trip + "/expenses",
        {"title": "Билет", "amount": "10", "activity_id": activity},
    )
    assert client.delete(trip).status_code == 204
    assert client.get(trip).status_code == 404
    with db.engine.connect() as conn:
        for table in (db.activities, db.expenses, db.packing_items):
            assert conn.execute(sa.select(table)).first() is None


def test_isolation(client, trip):
    activity = create(client, trip + "/activities", ACTIVITY)
    client.post("/api/auth/logout")
    create(client, "/api/auth/register", {**CREDS, "email": "other@example.com"})
    assert client.get("/api/trips").json() == []
    assert client.get(trip).status_code == 404
    assert client.put(trip, json=TRIP).status_code == 404
    assert client.delete(trip).status_code == 404
    other = "/api/trips/" + str(create(client, "/api/trips", TRIP))
    assert (
        client.post(
            other + "/expenses",
            json={"title": "Билет", "activity_id": activity, "amount": 1},
        ).status_code
        == 422
    )
    assert client.delete(f"{other}/activities/{activity}").status_code == 404


@pytest.mark.parametrize(
    "mutation", ["insert", "expense_trip", "expense_activity", "activity_trip"]
)
def test_database_rejects_cross_trip_expense(client, trip, mutation):
    trip_id = int(trip.rsplit("/", 1)[1])
    other_id = create(client, "/api/trips", TRIP)
    activity = create(client, trip + "/activities", ACTIVITY)
    other_activity = create(client, f"/api/trips/{other_id}/activities", ACTIVITY)
    expense = create(
        client,
        trip + "/expenses",
        {"title": "Билет", "amount": "10", "activity_id": activity},
    )

    # The deferred composite FK must reject the transaction even without the API.
    with pytest.raises(sa.exc.IntegrityError):
        with db.engine.begin() as conn:
            if mutation == "insert":
                conn.execute(
                    db.expenses.insert().values(
                        trip_id=other_id, activity_id=activity, title="Invalid", amount=1
                    )
                )
            elif mutation == "expense_trip":
                conn.execute(
                    db.expenses.update()
                    .where(db.expenses.c.id == expense)
                    .values(trip_id=other_id)
                )
            elif mutation == "expense_activity":
                conn.execute(
                    db.expenses.update()
                    .where(db.expenses.c.id == expense)
                    .values(activity_id=other_activity)
                )
            else:
                conn.execute(
                    db.activities.update()
                    .where(db.activities.c.id == activity)
                    .values(trip_id=other_id)
                )

    with db.engine.connect() as conn:
        saved = conn.execute(
            sa.select(db.expenses).where(db.expenses.c.id == expense)
        ).mappings().one()
        assert saved["trip_id"] == trip_id
        assert saved["activity_id"] == activity
        assert conn.scalar(sa.select(sa.func.count()).select_from(db.expenses)) == 1


def test_constraint_migration_preserves_existing_expenses(client, trip):
    activity = create(client, trip + "/activities", ACTIVITY)
    create(
        client, trip + "/expenses",
        {"title": "Билет", "amount": "10", "activity_id": activity},
    )
    create(client, trip + "/expenses", {"title": "Обед", "amount": "20"})
    before = client.get(trip).json()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.downgrade(config, "0001")
    command.upgrade(config, "head")
    assert client.get(trip).json() == before
    assert client.delete(f"{trip}/activities/{activity}").status_code == 204
    after = client.get(trip).json()
    assert all(e["activity_id"] is None for e in after["expenses"])
    assert after["total"] == before["total"]


def test_constraint_migration_reports_existing_invalid_link(client, trip):
    other_id = create(client, "/api/trips", TRIP)
    activity = create(client, trip + "/activities", ACTIVITY)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.downgrade(config, "0001")
    with db.engine.begin() as conn:
        expense_id = conn.execute(
            db.expenses.insert().values(
                trip_id=other_id, activity_id=activity, title="Imported", amount=10
            )
        ).inserted_primary_key[0]
    with pytest.raises(RuntimeError, match=f"Expense {expense_id} references"):
        command.upgrade(config, "head")
    with db.engine.begin() as conn:
        assert conn.scalar(
            sa.select(db.expenses.c.activity_id).where(db.expenses.c.id == expense_id)
        ) == activity
        conn.execute(
            db.expenses.update().where(db.expenses.c.id == expense_id)
            .values(activity_id=None)
        )
    command.upgrade(config, "head")
    assert client.get(f"/api/trips/{other_id}").json()["expenses"][0]["activity_id"] is None


def test_activity_time_precision(client, trip):
    values = {**ACTIVITY, "starts_at": "10:15:30.123456", "ends_at": "11:45:20.654321"}
    activity = create(client, trip + "/activities", values)
    assert client.put(
        f"{trip}/activities/{activity}", json={**values, "title": "Новое название"}
    ).status_code == 200
    saved = client.get(trip).json()["activities"][0]
    assert saved["title"] == "Новое название"
    assert saved["starts_at"] == values["starts_at"]
    assert saved["ends_at"] == values["ends_at"]


def test_migrations_match_metadata(client):
    with db.engine.connect() as conn:
        context = MigrationContext.configure(conn)
        assert compare_metadata(context, db.metadata) == []
