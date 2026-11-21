from datetime import date, time
from decimal import Decimal
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    model_validator,
)

Title = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]
Money = Annotated[Decimal, Field(max_digits=12, decimal_places=2, ge=0)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(Input):
    email: Annotated[EmailStr, Field(max_length=255)]
    password: Annotated[str, Field(min_length=8, max_length=128)]


class Trip(Input):
    title: Title
    destination: Title
    start_date: date
    end_date: date
    budget_limit: Money = Decimal(0)

    @model_validator(mode="after")
    def dates(self):
        if self.end_date < self.start_date:
            raise ValueError("Дата окончания раньше даты начала")
        return self


class Activity(Input):
    title: Title
    activity_date: date
    starts_at: time | None = None
    ends_at: time | None = None
    description: Annotated[str, Field(max_length=2000)] = ""

    @model_validator(mode="after")
    def times(self):
        if any(t and t.tzinfo for t in (self.starts_at, self.ends_at)):
            raise ValueError("Укажите местное время")
        if self.ends_at and (not self.starts_at or self.ends_at < self.starts_at):
            raise ValueError("Проверьте время начала и окончания")
        return self


class Expense(Input):
    title: Title
    amount: Annotated[Money, Field(gt=0)]
    activity_id: int | None = None


class Item(Input):
    name: Title
    is_packed: bool = False
