"""REST endpoints for the Accounts domain. Deterministic, non-LLM entry
point into accounts_server.py — the same business layer /chat uses via
accounts_tools.py, reached directly here instead of through the LangGraph
supervisor. Domain exceptions are left to propagate; main.py's global
exception handlers turn them into proper HTTP status codes.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from bank_platform import accounts_server
from bank_platform.admin_auth import require_admin

router = APIRouter(prefix="/accounts", tags=["accounts"])


class AccountResponse(BaseModel):
    id: str
    owner_name: str
    balance: float


class CreateAccountRequest(BaseModel):
    owner_name: str
    balance: float = 0


class UpdateAccountRequest(BaseModel):
    owner_name: str | None = None
    balance: float | None = None


@router.post("", response_model=AccountResponse, status_code=201)
async def create_account(body: CreateAccountRequest):
    return accounts_server.create_account(owner_name=body.owner_name, balance=body.balance)


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(account_id: str):
    return accounts_server.get_account(account_id)


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(account_id: str, body: UpdateAccountRequest):
    return accounts_server.update_account(account_id, owner_name=body.owner_name, balance=body.balance)


# Deliberately NOT wired into ACCOUNTS_TOOLS (accounts_tools.py) - closing
# an account is not a customer/agent self-service action. Gated by
# require_admin (admin_auth.py) - a static shared-secret header check, not
# real IAM (Phase 6, not started). Good enough to keep this unreachable by
# an ordinary caller in the meantime; replace when Phase 6 lands.
@router.delete("/{account_id}", response_model=AccountResponse, dependencies=[Depends(require_admin)])
async def delete_account(account_id: str):
    return accounts_server.delete_account(account_id)
