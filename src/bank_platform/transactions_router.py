"""REST endpoints for the Transactions domain. Deterministic, non-LLM entry
point into transactions_server.py. Create/list are nested under the owning
account (/accounts/{account_id}/transactions); get/update/delete address a
transaction directly by its own id, matching what the business layer takes
- no prefix is set on the router so both path shapes can coexist here.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from bank_platform import transactions_server

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
async def create_transaction(account_id: str, body: CreateTransactionRequest):
    return transactions_server.create_transaction(account_id, body.amount, body.description)


@router.get("/accounts/{account_id}/transactions", response_model=list[TransactionResponse])
async def list_transactions(account_id: str):
    return transactions_server.list_transactions(account_id)


@router.get("/transactions/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(transaction_id: str):
    return transactions_server.get_transaction(transaction_id)


@router.patch("/transactions/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(transaction_id: str, body: UpdateTransactionRequest):
    return transactions_server.update_transaction(transaction_id, amount=body.amount, description=body.description)


@router.delete("/transactions/{transaction_id}", response_model=TransactionResponse)
async def delete_transaction(transaction_id: str):
    return transactions_server.delete_transaction(transaction_id)
