"""Password hashing, JWTs, and the FastAPI dependencies that turn a bearer
token into a ``User``.

``require_user``/``require_user_qs`` are plain sync functions used as FastAPI
``Depends()`` — FastAPI runs sync dependencies in a threadpool automatically,
so the blocking SQLite/Postgres call here doesn't block the event loop
(same reasoning as ``run_in_threadpool`` around the blocking yt-dlp calls
elsewhere in this app).
"""

from __future__ import annotations

import time
import uuid

import bcrypt
import jwt
from fastapi import Header, HTTPException, Query
from sqlalchemy import select

from .config import JWT_SECRET, JWT_TTL_SECONDS
from .db import SessionLocal, User

JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": int(time.time()) + JWT_TTL_SECONDS}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    return payload.get("sub")


def register_user(email: str, password: str) -> User:
    email = email.strip().lower()
    with SessionLocal() as session:
        if session.scalar(select(User).where(User.email == email)) is not None:
            raise ValueError("an account with that email already exists")
        user = User(id=uuid.uuid4().hex[:16], email=email, password_hash=hash_password(password))
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def authenticate_user(email: str, password: str) -> User | None:
    email = email.strip().lower()
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email))
        if user is None or not verify_password(password, user.password_hash):
            return None
        return user


def get_user_by_id(user_id: str) -> User | None:
    with SessionLocal() as session:
        return session.get(User, user_id)


def _user_from_bearer(raw_token: str) -> User:
    user_id = decode_token(raw_token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="user no longer exists")
    return user


def require_user(authorization: str | None = Header(default=None)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    return _user_from_bearer(authorization.removeprefix("Bearer "))


def require_user_qs(authorization: str | None = Header(default=None), token: str | None = Query(default=None)) -> User:
    """Same as require_user, but also accepts ?token=... — for routes hit via
    direct browser navigation (file downloads), which can't set a header."""
    if authorization and authorization.startswith("Bearer "):
        return _user_from_bearer(authorization.removeprefix("Bearer "))
    if token:
        return _user_from_bearer(token)
    raise HTTPException(status_code=401, detail="missing token")
