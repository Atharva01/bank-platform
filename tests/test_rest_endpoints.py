import uuid

import pytest
from fastapi.testclient import TestClient

from bank_platform.auth import create_access_token, hash_password
from bank_platform.database import SessionLocal
from bank_platform.main import app
from bank_platform.models import Account, StaffUser

client = TestClient(app)


def _delete_account(account_id):
    session = SessionLocal()
    try:
        obj = session.get(Account, account_id)
        if obj is not None:
            session.delete(obj)
            session.commit()
    finally:
        session.close()


@pytest.fixture
def account():
    response = client.post("/accounts", json={"owner_name": "REST Test", "balance": 100})
    account_id = response.json()["id"]
    yield account_id
    _delete_account(account_id)


def test_create_and_get_account(account):
    response = client.get(f"/accounts/{account}")
    assert response.status_code == 200
    assert response.json()["owner_name"] == "REST Test"
    assert response.json()["balance"] == 100


def test_get_nonexistent_account_returns_404():
    response = client.get("/accounts/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error_type"] == "NotFoundError"


def test_create_account_with_negative_balance_returns_400():
    response = client.post("/accounts", json={"owner_name": "Bad Balance", "balance": -10})
    assert response.status_code == 400
    assert response.json()["error_type"] == "ValidationError"


def test_create_and_list_transactions(account):
    create_response = client.post(f"/accounts/{account}/transactions", json={"amount": 30, "description": "deposit"})
    assert create_response.status_code == 201
    assert create_response.json()["amount"] == 30

    list_response = client.get(f"/accounts/{account}/transactions")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    updated_account = client.get(f"/accounts/{account}")
    assert updated_account.json()["balance"] == 130


def test_overdraft_transaction_returns_422(account):
    response = client.post(f"/accounts/{account}/transactions", json={"amount": -500})
    assert response.status_code == 422
    assert response.json()["error_type"] == "InsufficientFundsError"


def test_get_nonexistent_transaction_returns_404():
    response = client.get("/transactions/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error_type"] == "NotFoundError"


def test_create_and_get_service_request(account):
    create_response = client.post(
        f"/accounts/{account}/service-requests", json={"request_type": "change_of_address"}
    )
    assert create_response.status_code == 201
    request_id = create_response.json()["id"]
    assert create_response.json()["status"] == "pending"

    get_response = client.get(f"/service-requests/{request_id}")
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "pending"


def test_invalid_status_transition_returns_409(account):
    create_response = client.post(
        f"/accounts/{account}/service-requests", json={"request_type": "kyc_update"}
    )
    request_id = create_response.json()["id"]

    response = client.patch(f"/service-requests/{request_id}", json={"status": "completed"})
    assert response.status_code == 409
    assert response.json()["error_type"] == "InvalidStatusTransitionError"


# Auth mechanics (login, token validation, unauthorized access) are
# covered in tests/test_auth.py - this file only needs a valid staff
# token to exercise the cascade-delete business logic below.
@pytest.fixture
def staff_token():
    username = f"cascade-test-{uuid.uuid4().hex[:8]}"
    user_id = str(uuid.uuid4())
    db = SessionLocal()
    db.add(StaffUser(id=user_id, username=username, hashed_password=hash_password("irrelevant")))
    db.commit()
    db.close()
    yield create_access_token(username)
    db = SessionLocal()
    row = db.get(StaffUser, user_id)
    if row is not None:
        db.delete(row)
        db.commit()
    db.close()


def test_delete_account_cascades_to_transactions_and_service_requests(account, staff_token):
    txn_response = client.post(f"/accounts/{account}/transactions", json={"amount": 30})
    transaction_id = txn_response.json()["id"]
    svc_response = client.post(f"/accounts/{account}/service-requests", json={"request_type": "kyc_update"})
    request_id = svc_response.json()["id"]

    delete_response = client.delete(f"/accounts/{account}", headers={"Authorization": f"Bearer {staff_token}"})
    assert delete_response.status_code == 200

    assert client.get(f"/accounts/{account}").status_code == 404
    assert client.get(f"/transactions/{transaction_id}").status_code == 404
    assert client.get(f"/service-requests/{request_id}").status_code == 404


def test_chat_endpoint_unaffected():
    # /chat is out of scope for this REST work - just confirm it's still
    # wired up (not asserting on LLM behavior here, no LLM call made).
    assert "/chat" in app.openapi()["paths"]
