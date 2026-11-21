from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
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
        sa.URL.create("sqlite", database=str(tmp_path / "travel.db"))
    )
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
