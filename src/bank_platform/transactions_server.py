"""Transactions MCP server (in-process). Owns the Transaction table AND
Account.balance — create/update/delete all atomically keep balance in sync
with the transaction ledger, including overdraft protection.
"""

from bank_platform import crud_transactions
from bank_platform.database import SessionLocal
from bank_platform.exceptions import NotFoundError


def _serialize(transaction) -> dict:
    return {
        "id": transaction.id,
        "account_id": transaction.account_id,
        "amount": float(transaction.amount),
        "description": transaction.description,
    }


def create_transaction(account_id: str, amount: float, description: str | None = None) -> dict:
    """Record a transaction against an account and atomically update its balance.
    A positive amount is a credit (deposit), a negative amount is a debit
    (withdrawal/payment). Fails if the debit would take the balance negative."""
    session = SessionLocal()
    try:
        transaction = crud_transactions.create_transaction_and_update_balance(
            session, account_id, amount, description
        )
        session.commit()
        return _serialize(transaction)
    finally:
        session.close()


def get_transaction(id: str) -> dict:
    """Look up a single transaction by its id."""
    session = SessionLocal()
    try:
        transaction = crud_transactions.get_transaction(session, id)
        if transaction is None:
            raise NotFoundError(f"Transaction {id} not found")
        return _serialize(transaction)
    finally:
        session.close()


def list_transactions(account_id: str) -> list[dict]:
    """List every transaction recorded against a given account (its statement)."""
    session = SessionLocal()
    try:
        transactions = crud_transactions.get_transactions_for_account(session, account_id)
        return [_serialize(t) for t in transactions]
    finally:
        session.close()


def update_transaction(id: str, amount: float | None = None, description: str | None = None) -> dict:
    """Edit an existing transaction's amount and/or description. If the amount
    changes, the linked account's balance is atomically re-adjusted to
    reverse the old amount's effect and apply the new one; fails if that
    would take the balance negative."""
    session = SessionLocal()
    try:
        transaction = crud_transactions.update_transaction_and_adjust_balance(
            session, id, amount=amount, description=description
        )
        session.commit()
        return _serialize(transaction)
    finally:
        session.close()


def delete_transaction(id: str) -> dict:
    """Delete a transaction and atomically reverse its effect on the linked
    account's balance. Fails if reversing it would take the balance negative."""
    session = SessionLocal()
    try:
        transaction = crud_transactions.delete_transaction_and_adjust_balance(session, id)
        session.commit()
        return _serialize(transaction)
    finally:
        session.close()
