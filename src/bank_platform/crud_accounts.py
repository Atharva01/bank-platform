from sqlalchemy import delete as sa_delete
from sqlalchemy import update
from sqlalchemy.orm import Session

from bank_platform.models import Account, ServiceRequest, Transaction


def create_account(session: Session, owner_name: str, balance: float = 0):
    account = Account(owner_name=owner_name, balance=balance)
    session.add(account)
    session.flush()
    return account


def get_account(session: Session, account_id: str):
    return session.get(Account, account_id)


def update_account(
    session: Session,
    account_id: str,
    owner_name: str | None = None,
    balance: float | None = None,
):
    update_data = {}

    if isinstance(owner_name, str):
        update_data["owner_name"] = owner_name

    if isinstance(balance, (float, int)):
        update_data["balance"] = balance

    if update_data:
        statement = update(Account).where(Account.id == account_id).values(**update_data)
        session.execute(statement)
        session.flush()

    return get_account(session, account_id)


def delete_account(session: Session, account_id: str):
    """Deletes the account and cascades to its transactions and service
    requests in the same transaction - both tables reference account_id
    with no DB-level foreign key/cascade (Account is deleted by
    accounts_server, but owned by neither transactions_server nor
    service_server), so this was previously leaving orphaned rows behind."""
    account = session.get(Account, account_id)
    if account is None:
        return None

    session.execute(sa_delete(Transaction).where(Transaction.account_id == account_id))
    session.execute(sa_delete(ServiceRequest).where(ServiceRequest.account_id == account_id))
    session.delete(account)
    session.flush()

    return account
