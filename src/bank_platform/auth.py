"""Staff (Phase 6) and customer (added later, at explicit user direction -
see account-schema-redesign-deferred memory) authentication. Both are
bearer-token (JWT) based: a login endpoint verifies a password and issues
a signed token; a get_current_*_user dependency validates that token and
re-fetches the real user on every protected request.

Staff and customer are deliberately separate identity kinds (StaffUser vs
Customer, admin_auth.py's replacement vs a real login for the actual
public-facing user) - a JWT carries a "typ" claim ("staff"/"customer") so
the two are never structurally interchangeable; a leaked/reused token from
one kind can't pass the other kind's dependency.

Customer auth adds only a login credential and an Account -> Customer
ownership link (Account.customer_id). It does not redesign
Account.owner_name or resolve the "two Alices" identity-uniqueness
question - that research is still separately deferred.
"""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select

from bank_platform.database import SessionLocal
from bank_platform.models import Customer, StaffUser

ACCESS_TOKEN_EXPIRE_MINUTES = 60  # session length for both identity kinds -
# unrelated to graph.py's 10-minute customer *chat* idle timeout, a
# different concept (login session vs. conversation continuity)
_JWT_ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
customer_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/customers/login")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(subject: str, token_type: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "typ": token_type, "exp": expire}
    return jwt.encode(payload, os.environ["JWT_SECRET_KEY"], algorithm=_JWT_ALGORITHM)


def _decode_subject(token: str, expected_type: str) -> str:
    credentials_error = HTTPException(status_code=401, detail="Could not validate credentials")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET_KEY"], algorithms=[_JWT_ALGORITHM])
        subject = payload.get("sub")
        if subject is None or payload.get("typ") != expected_type:
            raise credentials_error
        return subject
    except jwt.PyJWTError:
        raise credentials_error


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
    username = _decode_subject(token, expected_type="staff")
    credentials_error = HTTPException(status_code=401, detail="Could not validate credentials")
    db = SessionLocal()
    try:
        user = db.execute(select(StaffUser).where(StaffUser.username == username)).scalar_one_or_none()
        if user is None:
            raise credentials_error
        return user
    finally:
        db.close()


def authenticate_customer(username: str, password: str) -> Customer | None:
    """Same shape as authenticate_staff_user - same enumeration-safety
    reasoning applies (don't distinguish unknown username from wrong
    password in the response)."""
    db = SessionLocal()
    try:
        user = db.execute(select(Customer).where(Customer.username == username)).scalar_one_or_none()
        if user is None or not verify_password(password, user.hashed_password):
            return None
        return user
    finally:
        db.close()


def get_current_customer(token: str = Depends(customer_oauth2_scheme)) -> Customer:
    """FastAPI dependency gating /chat and the account/transaction/service
    REST surface. Same re-fetch-every-request pattern as
    get_current_staff_user, for the same reason (immediate revocation)."""
    username = _decode_subject(token, expected_type="customer")
    credentials_error = HTTPException(status_code=401, detail="Could not validate credentials")
    db = SessionLocal()
    try:
        user = db.execute(select(Customer).where(Customer.username == username)).scalar_one_or_none()
        if user is None:
            raise credentials_error
        return user
    finally:
        db.close()
