"""Transactions MCP server (in-process). Owns the Transaction table AND
Account.balance — create/update/delete all atomically keep balance in sync
with the transaction ledger, including overdraft protection.
"""

import crud_transactions
from database import SessionLocal
from exceptions import NotFoundError


def _serialize(transaction) -> dict:
    return {
        "id": transaction.id,
        "account_id": transaction.account_id,
        "amount": float(transaction.amount),
        "description": transaction.description,
    }


def create_transaction(account_id, amount, description=None) -> dict:
    session = SessionLocal()
    try:
        transaction = crud_transactions.create_transaction_and_update_balance(
            session, account_id, amount, description
        )
        session.commit()
        return _serialize(transaction)
    finally:
        session.close()


def get_transaction(id) -> dict:
    session = SessionLocal()
    try:
        transaction = crud_transactions.get_transaction(session, id)
        if transaction is None:
            raise NotFoundError(f"Transaction {id} not found")
        return _serialize(transaction)
    finally:
        session.close()


def list_transactions(account_id) -> list[dict]:
    session = SessionLocal()
    try:
        transactions = crud_transactions.get_transactions_for_account(session, account_id)
        return [_serialize(t) for t in transactions]
    finally:
        session.close()


def update_transaction(id, amount=None, description=None) -> dict:
    session = SessionLocal()
    try:
        transaction = crud_transactions.update_transaction_and_adjust_balance(
            session, id, amount=amount, description=description
        )
        session.commit()
        return _serialize(transaction)
    finally:
        session.close()


def delete_transaction(id) -> dict:
    session = SessionLocal()
    try:
        transaction = crud_transactions.delete_transaction_and_adjust_balance(session, id)
        session.commit()
        return _serialize(transaction)
    finally:
        session.close()
