"""REST endpoints for the Transactions domain. Deterministic, non-LLM entry
point into transactions_server.py. Create/list are nested under the owning
account (/accounts/{account_id}/transactions); get/update/delete address a
transaction directly by its own id, matching what the business layer takes
- no prefix is set on the router so both path shapes can coexist here.

Every endpoint requires a real customer (Depends(get_current_customer)) and
enforces ownership via authz.py - added to close the gap where any
anonymous caller could act on any account_id/transaction_id it named (see
account-schema-redesign-deferred memory's 2026-09-12 update).
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from bank_platform import authz, transactions_server
from bank_platform.auth import get_current_customer
from bank_platform.exceptions import NotFoundError
from bank_platform.models import Customer

router = APIRouter(tags=["transactions"])


class TransactionResponse(BaseModel):
    id: str
    account_id: str
    amount: float
    description: str | None


class CreateTransactionRequest(BaseModel):
    amount: float
    description: str | None = None


class UpdateTransactionRequest(BaseModel):
    amount: float | None = None
    description: str | None = None


@router.post("/accounts/{account_id}/transactions", response_model=TransactionResponse, status_code=201)
async def create_transaction(
    account_id: str, body: CreateTransactionRequest, current_customer: Customer = Depends(get_current_customer)
):
    authz.require_owner(account_id, current_customer.id)
    return transactions_server.create_transaction(account_id, body.amount, body.description)


@router.get("/accounts/{account_id}/transactions", response_model=list[TransactionResponse])
async def list_transactions(account_id: str, current_customer: Customer = Depends(get_current_customer)):
    authz.require_owner(account_id, current_customer.id)
    return transactions_server.list_transactions(account_id)


def _require_owns_transaction(transaction_id: str, customer_id: str) -> None:
    account_id = transactions_server.get_transaction_account_id(transaction_id)
    # None (transaction doesn't exist) is handled identically to "not
    # yours" by require_owner via get_account_owner's own None handling -
    # but a None account_id here means there's nothing to look up at all,
    # so raise the same NotFoundError directly instead of querying "".
    if account_id is None:
        raise NotFoundError(f"Transaction {transaction_id} not found")
    authz.require_owner(account_id, customer_id)


@router.get("/transactions/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(transaction_id: str, current_customer: Customer = Depends(get_current_customer)):
    _require_owns_transaction(transaction_id, current_customer.id)
    return transactions_server.get_transaction(transaction_id)


@router.patch("/transactions/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: str, body: UpdateTransactionRequest, current_customer: Customer = Depends(get_current_customer)
):
    _require_owns_transaction(transaction_id, current_customer.id)
    return transactions_server.update_transaction(transaction_id, amount=body.amount, description=body.description)


@router.delete("/transactions/{transaction_id}", response_model=TransactionResponse)
async def delete_transaction(transaction_id: str, current_customer: Customer = Depends(get_current_customer)):
    _require_owns_transaction(transaction_id, current_customer.id)
    return transactions_server.delete_transaction(transaction_id)
