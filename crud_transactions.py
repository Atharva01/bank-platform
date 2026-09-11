from sqlalchemy import select, update
from sqlalchemy.orm import Session

from models import Transaction


def create_transaction(
    session: Session, account_id: str, amount: float, description: str | None = None
):
    transaction = Transaction(account_id=account_id, amount=amount, description=description)
    session.add(transaction)
    session.flush()
    return transaction


def get_transaction(session: Session, transaction_id: str):
    return session.get(Transaction, transaction_id)


def get_transactions_for_account(session: Session, account_id: str):
    statement = select(Transaction).where(Transaction.account_id == account_id)
    result = session.execute(statement)
    return result.scalars().all()


def update_transaction(
    session: Session,
    transaction_id: str,
    amount: float | None = None,
    description: str | None = None,
):
    update_data = {}

    if isinstance(amount, (float, int)):
        update_data["amount"] = amount

    if isinstance(description, str):
        update_data["description"] = description

    if update_data:
        statement = (
            update(Transaction).where(Transaction.id == transaction_id).values(**update_data)
        )
        session.execute(statement)
        session.flush()

    return get_transaction(session, transaction_id)


def delete_transaction(session: Session, transaction_id: str):
    transaction = session.get(Transaction, transaction_id)
    if transaction is None:
        return None

    session.delete(transaction)
    session.flush()

    return transaction
