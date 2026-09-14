"""REST endpoints for the Accounts domain. Deterministic, non-LLM entry
point into accounts_server.py — the same business layer /chat uses via
accounts_tools.py, reached directly here instead of through the LangGraph
supervisor. Domain exceptions are left to propagate; main.py's global
exception handlers turn them into proper HTTP status codes.

Every endpoint except the staff-gated DELETE requires a real customer
(Depends(get_current_customer)) and enforces ownership via authz.py -
added to close the gap where any anonymous caller could act on any
account_id it named (see account-schema-redesign-deferred memory's
2026-09-12 update).
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from bank_platform import accounts_server, authz
from bank_platform.auth import get_current_customer, get_current_staff_user
from bank_platform.models import Customer

router = APIRouter(prefix="/accounts", tags=["accounts"])


class AccountResponse(BaseModel):
    id: str
    owner_name: str
    balance: float


class CreateAccountRequest(BaseModel):
    owner_name: str
    balance: float = 0


class UpdateAccountRequest(BaseModel):
    # No `balance` field - a customer changes their balance only via a
    # Transaction (transactions_router.py), never directly. Letting a
    # customer PATCH their own balance bypassed the atomic, ledger-linked
    # balance adjustment transactions_server.py exists to enforce (found
    # in Phase 10's security review - see PROBLEMS.md).
    owner_name: str | None = None


@router.post("", response_model=AccountResponse, status_code=201)
async def create_account(body: CreateAccountRequest, current_customer: Customer = Depends(get_current_customer)):
    return accounts_server.create_account(
        owner_name=body.owner_name, balance=body.balance, customer_id=current_customer.id
    )


@router.get("", response_model=list[AccountResponse])
async def list_my_accounts(current_customer: Customer = Depends(get_current_customer)):
    """Lists the caller's own accounts - once a customer can have more than
    one, they can't just guess/memorize ids (see the new list_accounts
    chat tool's identical reasoning in accounts_tools.py)."""
    return accounts_server.list_accounts_for_customer(current_customer.id)


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(account_id: str, current_customer: Customer = Depends(get_current_customer)):
    authz.require_owner(account_id, current_customer.id)
    return accounts_server.get_account(account_id)


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: str, body: UpdateAccountRequest, current_customer: Customer = Depends(get_current_customer)
):
    authz.require_owner(account_id, current_customer.id)
    return accounts_server.update_account(account_id, owner_name=body.owner_name)


# Deliberately NOT wired into ACCOUNTS_TOOLS (accounts_tools.py) - closing
# an account is not a customer/agent self-service action. Gated by
# get_current_staff_user (auth.py) - real staff authentication (Phase 6),
# replacing the earlier static shared-secret stopgap. Staff bypasses
# customer ownership entirely for this one action - unchanged, unrelated
# to the customer-auth work above.
@router.delete("/{account_id}", response_model=AccountResponse, dependencies=[Depends(get_current_staff_user)])
async def delete_account(account_id: str):
    return accounts_server.delete_account(account_id)
