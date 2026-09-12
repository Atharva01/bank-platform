"""Customer login (added at explicit user direction to close the gap
where any anonymous caller could act on any account_id it named - see
account-schema-redesign-deferred memory). Mirrors auth_router.py's staff
login, but customers self-register (staff accounts are provisioned by
hand via scripts/create_staff_user.py; customers aren't).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select

from bank_platform.auth import authenticate_customer, create_access_token, hash_password
from bank_platform.database import SessionLocal
from bank_platform.models import Customer
from bank_platform.rate_limit import limiter

router = APIRouter(prefix="/customers", tags=["customers"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    username: str
    password: str


@router.post("/register", response_model=TokenResponse, status_code=201)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest):
    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username must not be empty.")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    db = SessionLocal()
    try:
        if db.execute(select(Customer).where(Customer.username == username)).scalar_one_or_none():
            raise HTTPException(status_code=409, detail="A customer with that username already exists.")
        db.add(Customer(id=str(uuid.uuid4()), username=username, hashed_password=hash_password(body.password)))
        db.commit()
    finally:
        db.close()

    # Return a token immediately - the customer can go straight to opening
    # an account without a redundant second login call.
    return TokenResponse(access_token=create_access_token(username, "customer"))


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_customer(form_data.username, form_data.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    return TokenResponse(access_token=create_access_token(user.username, "customer"))
