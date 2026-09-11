"""Staff login (Phase 6 - Auth & Authorisation). The only public
authentication endpoint in the app - there's no customer-facing login
(see auth.py's module docstring for why).
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from bank_platform.auth import authenticate_staff_user, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_staff_user(form_data.username, form_data.password)
    if user is None:
        # Deliberately the same error for "no such user" and "wrong
        # password" - distinguishing them would let a caller enumerate
        # valid usernames.
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    return TokenResponse(access_token=create_access_token(user.username))
