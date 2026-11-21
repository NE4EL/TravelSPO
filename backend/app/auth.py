import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy import Connection, select
from sqlalchemy.exc import IntegrityError

from .db import sessions, transaction, users
from .schemas import Credentials

router = APIRouter(prefix="/api/auth")
DB = Annotated[Connection, Depends(transaction, scope="function")]
Token = Annotated[str | None, Cookie(alias="session")]
lifetime = timedelta(days=7)


def now():
    return datetime.now(UTC).replace(tzinfo=None)


def password_hash(password, salt):
    key = hashlib.scrypt(
        password.encode(),
        salt=bytes.fromhex(salt),
        n=2**15,
        r=8,
        p=1,
        maxmem=64 * 1024 * 1024,
    )
    return salt + "." + key.hex()


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(db: DB, session: Token = None):
    row = (
        db.execute(
            select(users.c.id, users.c.email)
            .join(sessions)
            .where(
                sessions.c.digest == digest(session or ""),
                sessions.c.expires_at > now(),
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise HTTPException(401, "Войдите в аккаунт")
    return dict(row)


User = Annotated[dict, Depends(current_user, scope="function")]


def start_session(db, user, response):
    token = secrets.token_urlsafe(32)
    db.execute(
        sessions.insert().values(
            user_id=user["id"], digest=digest(token), expires_at=now() + lifetime
        )
    )
    response.set_cookie(
        "session",
        token,
        httponly=True,
        samesite="strict",
        path="/api",
        secure=os.getenv("COOKIE_SECURE") == "1",
        max_age=int(lifetime.total_seconds()),
    )
    return {"id": user["id"], "email": user["email"]}


@router.post("/register", status_code=201)
def register(data: Credentials, db: DB, response: Response):
    email = data.email.lower()
    try:
        result = db.execute(
            users.insert().values(
                email=email,
                password_hash=password_hash(data.password, secrets.token_hex(16)),
            )
        )
    except IntegrityError:
        raise HTTPException(409, "Этот email уже зарегистрирован")
    return start_session(
        db, {"id": result.inserted_primary_key[0], "email": email}, response
    )


@router.post("/login")
def login(data: Credentials, db: DB, response: Response):
    user = (
        db.execute(select(users).where(users.c.email == data.email.lower()))
        .mappings()
        .first()
    )
    stored = user["password_hash"] if user else "00" * 16 + "." + "00" * 64
    if (
        not hmac.compare_digest(
            password_hash(data.password, stored.split(".")[0]), stored
        )
        or not user
    ):
        raise HTTPException(401, "Неверный email или пароль")
    return start_session(db, user, response)


@router.get("/me")
def me(user: User):
    return user


@router.post("/logout", status_code=204)
def logout(db: DB, response: Response, session: Token = None):
    db.execute(sessions.delete().where(sessions.c.digest == digest(session or "")))
    response.delete_cookie("session", path="/api")
