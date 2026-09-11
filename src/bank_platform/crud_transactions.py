from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from bank_platform.exceptions import InsufficientFundsError, NotFoundError, ValidationError
from bank_platform.models import Account, Transaction


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


def update_transaction_and_adjust_balance(
    session: Session,
    transaction_id: str,
    amount=None,
    description: str | None = None,
):
    """Atomically edits a transaction, reversing its old balance effect and
    applying the new one if amount changes. Raises NotFoundError if the
    transaction or its account doesn't exist, InsufficientFundsError if the
    new amount would take the balance negative.
    """
    transaction = session.get(Transaction, transaction_id)
    if transaction is None:
        raise NotFoundError(f"Transaction {transaction_id} not found")

    if amount is not None:
        try:
            new_amount = Decimal(str(amount))
        except InvalidOperation:
            raise ValidationError(f"amount must be a number, got {amount!r}")
        if new_amount == 0:
            raise ValidationError("amount must not be zero")

        account = session.get(Account, transaction.account_id)
        if account is None:
            raise NotFoundError(f"Account {transaction.account_id} not found")

        delta = new_amount - transaction.amount
        new_balance = account.balance + delta
        if new_balance < 0:
            raise InsufficientFundsError(
                f"Insufficient funds: balance {account.balance}, delta {delta}"
            )
        account.balance = new_balance
        transaction.amount = new_amount

    if description is not None:
        transaction.description = description

    session.flush()
    return transaction


def delete_transaction_and_adjust_balance(session: Session, transaction_id: str):
    """Atomically deletes a transaction and reverses its balance effect.
    Raises NotFoundError if the transaction or its account doesn't exist,
    InsufficientFundsError if reversing it would take the balance negative.
    """
    transaction = session.get(Transaction, transaction_id)
    if transaction is None:
        raise NotFoundError(f"Transaction {transaction_id} not found")

    account = session.get(Account, transaction.account_id)
    if account is None:
        raise NotFoundError(f"Account {transaction.account_id} not found")

    new_balance = account.balance - transaction.amount
    if new_balance < 0:
        raise InsufficientFundsError(
            f"Deleting this transaction would leave balance at {new_balance}"
        )

    account.balance = new_balance
    session.delete(transaction)
    session.flush()
    return transaction
