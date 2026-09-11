from decimal import Decimal, InvalidOperation

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from exceptions import InsufficientFundsError, NotFoundError, ValidationError
from models import Account, Transaction


def create_transaction_and_update_balance(
    session: Session, account_id: str, amount, description: str | None = None
):
    """Atomically writes the transaction and adjusts the account's balance.

    amount > 0 is a credit (deposit), amount < 0 is a debit (withdrawal).
    Raises NotFoundError if account_id doesn't exist, InsufficientFundsError
    if the debit would take the balance negative.
    """
    try:
        amount = Decimal(str(amount))
    except InvalidOperation:
        raise ValidationError(f"amount must be a number, got {amount!r}")

    if amount == 0:
        raise ValidationError("amount must not be zero")

    account = session.get(Account, account_id)
    if account is None:
        raise NotFoundError(f"Account {account_id} not found")

    new_balance = account.balance + amount
    if new_balance < 0:
        raise InsufficientFundsError(
            f"Insufficient funds: balance {account.balance}, requested {amount}"
        )

    account.balance = new_balance
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
