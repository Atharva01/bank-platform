"""Accounts MCP server (in-process). Owns the Account table and its
invariants: owner_name/balance validation. Each tool call is one atomic
DB transaction — no session is ever shared across two calls.
"""

from bank_platform import crud_accounts
from bank_platform.database import SessionLocal
from bank_platform.exceptions import NotFoundError, ValidationError


def _invalid_owner_name(owner_name) -> bool:
    return not isinstance(owner_name, str) or not owner_name.strip()


def _invalid_balance(balance) -> bool:
    return not isinstance(balance, (int, float)) or isinstance(balance, bool) or balance < 0


def _serialize(account) -> dict:
    return {"id": account.id, "owner_name": account.owner_name, "balance": float(account.balance)}


def create_account(owner_name: str, balance: float = 0) -> dict:
    """Open a new bank account for the given owner, with an optional starting balance."""
    if _invalid_owner_name(owner_name):
        raise ValidationError("owner_name must be a non-empty string")
    if _invalid_balance(balance):
        raise ValidationError("balance must not be negative")

    session = SessionLocal()
    try:
        account = crud_accounts.create_account(session, owner_name, balance)
        session.commit()
        return _serialize(account)
    finally:
        session.close()


def get_account(id: str) -> dict:
    """Look up an account by its id and return its owner name and balance."""
    session = SessionLocal()
    try:
        account = crud_accounts.get_account(session, id)
        if account is None:
            raise NotFoundError(f"Account {id} not found")
        return _serialize(account)
    finally:
        session.close()


def update_account(id: str, owner_name: str | None = None, balance: float | None = None) -> dict:
    """Update an existing account's owner name and/or balance. Only the fields
    provided are changed; omit a field to leave it as-is."""
    if owner_name is not None and _invalid_owner_name(owner_name):
        raise ValidationError("owner_name must be a non-empty string")
    if balance is not None and _invalid_balance(balance):
        raise ValidationError("balance must not be negative")

    session = SessionLocal()
    try:
        account = crud_accounts.update_account(session, id, owner_name=owner_name, balance=balance)
        if account is None:
            raise NotFoundError(f"Account {id} not found")
        session.commit()
        return _serialize(account)
    finally:
        session.close()


def delete_account(id: str) -> dict:
    """Permanently close and delete an account by its id."""
    session = SessionLocal()
    try:
        account = crud_accounts.delete_account(session, id)
        if account is None:
            raise NotFoundError(f"Account {id} not found")
        session.commit()
        return _serialize(account)
    finally:
        session.close()
