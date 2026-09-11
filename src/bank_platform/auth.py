"""Real staff/admin authentication (Phase 6 - Auth & Authorisation),
replacing admin_auth.py's static shared-secret gate. Bearer-token (JWT)
based: POST /auth/login (auth_router.py) verifies a StaffUser's password
and issues a signed token; get_current_staff_user validates that token
and looks up the real user on every protected request.

Customer-facing auth is explicitly out of scope - there's no Customer/User
identity model in this app yet (Account.owner_name is just a free string),
and building one is a separate, deferred decision (see PROGRESS.md
Phase 6 and the account-schema-redesign-deferred memory). This only
replaces the one thing that existed before: an admin/staff gate.
"""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select

from bank_platform.database import SessionLocal
from bank_platform.models import StaffUser

ACCESS_TOKEN_EXPIRE_MINUTES = 60  # staff session length - unrelated to
# graph.py's 10-minute customer chat idle timeout, a different concept
_JWT_ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, os.environ["JWT_SECRET_KEY"], algorithm=_JWT_ALGORITHM)


def authenticate_staff_user(username: str, password: str) -> StaffUser | None:
    """Looks up a staff user and verifies their password. Returns None on
    any failure (unknown username or wrong password) - callers must not
    distinguish which in their response, so a login attempt can't be used
    to enumerate valid usernames."""
    db = SessionLocal()
    try:
        user = db.execute(select(StaffUser).where(StaffUser.username == username)).scalar_one_or_none()
        if user is None or not verify_password(password, user.hashed_password):
            return None
        return user
    finally:
        db.close()


def get_current_staff_user(token: str = Depends(oauth2_scheme)) -> StaffUser:
    """FastAPI dependency - the direct replacement for admin_auth.py's
    require_admin. Decodes/validates the JWT and re-fetches the real
    StaffUser row on every request (not just trusting the token's
    claims), so a deleted staff account stops working immediately rather
    than staying valid until the token expires."""
    credentials_error = HTTPException(status_code=401, detail="Could not validate credentials")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET_KEY"], algorithms=[_JWT_ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_error
    except jwt.PyJWTError:
        raise credentials_error

    db = SessionLocal()
    try:
        user = db.execute(select(StaffUser).where(StaffUser.username == username)).scalar_one_or_none()
        if user is None:
            raise credentials_error
        return user
    finally:
        db.close()
