"""Accounts MCP server (in-process). Owns the Account table and its
invariants: owner_name/balance validation. Each tool call is one atomic
DB transaction — no session is ever shared across two calls.
"""

import crud_accounts
from database import SessionLocal
from exceptions import NotFoundError, ValidationError


def _invalid_owner_name(owner_name) -> bool:
    return not isinstance(owner_name, str) or not owner_name.strip()


def _invalid_balance(balance) -> bool:
    return not isinstance(balance, (int, float)) or isinstance(balance, bool) or balance < 0


def _serialize(account) -> dict:
    return {"id": account.id, "owner_name": account.owner_name, "balance": float(account.balance)}


def create_account(owner_name, balance=0) -> dict:
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


def get_account(id) -> dict:
    session = SessionLocal()
    try:
        account = crud_accounts.get_account(session, id)
        if account is None:
            raise NotFoundError(f"Account {id} not found")
        return _serialize(account)
    finally:
        session.close()


def update_account(id, owner_name=None, balance=None) -> dict:
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


def delete_account(id) -> dict:
    session = SessionLocal()
    try:
        account = crud_accounts.delete_account(session, id)
        if account is None:
            raise NotFoundError(f"Account {id} not found")
        session.commit()
        return _serialize(account)
    finally:
        session.close()
