from decimal import Decimal
from os import environ
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from . import schemas
from .auth import DB, User, router
from .db import activities, expenses, packing_items, trips

app = FastAPI(title="TravelPlanner", version="1.0")
app.include_router(router)


@app.exception_handler(RequestValidationError)
async def invalid_input(request: Request, exc: RequestValidationError):
    error = exc.errors()[0]
    message = error["msg"].removeprefix("Value error, ")
    labels = {
        "email": "Введите корректный email",
        "password": "Пароль должен содержать 8–128 символов",
        "amount": "Введите положительную сумму с точностью до копейки",
        "budget_limit": "Введите неотрицательный бюджет с точностью до копейки",
        "title": "Введите название длиной до 120 символов",
        "name": "Введите название вещи",
        "destination": "Укажите направление поездки",
    }
    if error["loc"][-1] != "body":
        message = labels.get(error["loc"][-1], "Проверьте значение поля")
    return JSONResponse({"detail": message}, status_code=422)


def owned_trip(trip_id: int, db: DB, user: User, request: Request):
    query = select(trips).where(trips.c.id == trip_id, trips.c.user_id == user["id"])
    query = query.with_for_update(read=request.method == "GET")
    row = db.execute(query).mappings().first()
    if not row:
        raise HTTPException(404, "Поездка не найдена")
    return row


Owned = Annotated[dict, Depends(owned_trip, scope="function")]
base = "/api/trips/{trip_id}"


def records(db, query):
    return [dict(row) for row in db.execute(query).mappings()]


@app.get("/api/trips")
def list_trips(db: DB, user: User):
    return records(
        db,
        select(trips)
        .where(trips.c.user_id == user["id"])
        .order_by(trips.c.start_date, trips.c.id),
    )


@app.post("/api/trips", status_code=201)
def create_trip(data: schemas.Trip, db: DB, user: User):
    result = db.execute(trips.insert().values(user_id=user["id"], **data.model_dump()))
    return {"id": result.inserted_primary_key[0]}


@app.get(base)
def get_trip(db: DB, trip: Owned):
    trip_id = trip["id"]
    schedule = records(
        db,
        select(activities)
        .where(activities.c.trip_id == trip_id)
        .order_by(
            activities.c.activity_date,
            activities.c.starts_at.asc().nulls_last(),
            activities.c.id,
        ),
    )
    costs = records(
        db,
        select(expenses).where(expenses.c.trip_id == trip_id).order_by(expenses.c.id),
    )
    items = records(
        db,
        select(packing_items)
        .where(packing_items.c.trip_id == trip_id)
        .order_by(packing_items.c.sort_order, packing_items.c.id),
    )
    total = sum((cost["amount"] for cost in costs), Decimal("0.00"))
    return {
        **trip,
        "activities": schedule,
        "expenses": costs,
        "packing_items": items,
        "total": str(total),
        "remaining": str(trip["budget_limit"] - total),
    }


@app.put(base, status_code=204)
def update_trip(data: schemas.Trip, db: DB, trip: Owned):
    outside = (
        select(activities.c.id)
        .where(
            activities.c.trip_id == trip["id"],
            ~activities.c.activity_date.between(data.start_date, data.end_date),
        )
        .limit(1)
    )
    if db.scalar(outside):
        raise HTTPException(
            422, "Сначала перенесите мероприятия, выходящие за новые даты поездки"
        )
    db.execute(
        trips.update().where(trips.c.id == trip["id"]).values(**data.model_dump())
    )


@app.delete(base, status_code=204)
def delete_trip(db: DB, trip: Owned):
    db.execute(trips.delete().where(trips.c.id == trip["id"]))


def save_child(db, table, trip_id, values, row_id=None):
    if row_id is None:
        result = db.execute(table.insert().values(trip_id=trip_id, **values))
        return {"id": result.inserted_primary_key[0]}
    statement = (
        table.update()
        .where(table.c.trip_id == trip_id, table.c.id == row_id)
        .values(**values)
    )
    if not db.execute(statement).rowcount:
        raise HTTPException(404, "Запись не найдена")
    return {"id": row_id}


def activity_values(trip, data):
    if not trip["start_date"] <= data.activity_date <= trip["end_date"]:
        raise HTTPException(422, "Дата мероприятия должна входить в период поездки")
    return data.model_dump()


@app.post(base + "/activities", status_code=201)
def add_activity(data: schemas.Activity, db: DB, trip: Owned):
    return save_child(db, activities, trip["id"], activity_values(trip, data))


@app.put(base + "/activities/{row_id}")
def edit_activity(row_id: int, data: schemas.Activity, db: DB, trip: Owned):
    return save_child(db, activities, trip["id"], activity_values(trip, data), row_id)


def expense_values(db, trip, data):
    if data.activity_id is not None and not db.scalar(
        select(activities.c.id).where(
            activities.c.id == data.activity_id, activities.c.trip_id == trip["id"]
        )
    ):
        raise HTTPException(422, "Выберите мероприятие этой поездки")
    return data.model_dump()


@app.post(base + "/expenses", status_code=201)
def add_expense(data: schemas.Expense, db: DB, trip: Owned):
    return save_child(db, expenses, trip["id"], expense_values(db, trip, data))


@app.put(base + "/expenses/{row_id}")
def edit_expense(row_id: int, data: schemas.Expense, db: DB, trip: Owned):
    return save_child(db, expenses, trip["id"], expense_values(db, trip, data), row_id)


@app.post(base + "/items", status_code=201)
def add_item(data: schemas.Item, db: DB, trip: Owned):
    last = db.scalar(
        select(func.max(packing_items.c.sort_order)).where(
            packing_items.c.trip_id == trip["id"]
        )
    )
    return save_child(
        db,
        packing_items,
        trip["id"],
        {**data.model_dump(), "sort_order": (last or 0) + 1},
    )


@app.put(base + "/items/{row_id}")
def edit_item(row_id: int, data: schemas.Item, db: DB, trip: Owned):
    return save_child(db, packing_items, trip["id"], data.model_dump(), row_id)


@app.delete(base + "/{collection}/{row_id}", status_code=204)
def delete_child(collection: str, row_id: int, db: DB, trip: Owned):
    table = {
        "activities": activities,
        "expenses": expenses,
        "items": packing_items,
    }.get(collection)
    if (
        table is None
        or not db.execute(
            table.delete().where(table.c.trip_id == trip["id"], table.c.id == row_id)
        ).rowcount
    ):
        raise HTTPException(404, "Запись не найдена")


# The container serves the compiled web client and the API on one origin.
if "FRONTEND_DIST" in environ:
    app.mount(
        "/", StaticFiles(directory=environ["FRONTEND_DIST"], html=True), name="frontend"
    )
