import uuid

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from bank_platform.auth import _JWT_ALGORITHM, create_access_token, hash_password
from bank_platform.database import SessionLocal
from bank_platform.main import app
from bank_platform.models import Account, StaffUser

client = TestClient(app)

_TEST_USERNAME = "test-staff"
_TEST_PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def staff_user():
    db = SessionLocal()
    user = StaffUser(id=str(uuid.uuid4()), username=_TEST_USERNAME, hashed_password=hash_password(_TEST_PASSWORD))
    db.add(user)
    db.commit()
    db.close()
    yield
    db = SessionLocal()
    row = db.execute(select(StaffUser).where(StaffUser.username == _TEST_USERNAME)).scalar_one_or_none()
    if row is not None:
        db.delete(row)
        db.commit()
    db.close()


@pytest.fixture
def account():
    response = client.post("/accounts", json={"owner_name": "Auth Test", "balance": 50})
    account_id = response.json()["id"]
    yield account_id
    db = SessionLocal()
    obj = db.get(Account, account_id)
    if obj is not None:
        db.delete(obj)
        db.commit()
    db.close()


def test_login_with_correct_credentials_returns_a_token(staff_user):
    response = client.post("/auth/login", data={"username": _TEST_USERNAME, "password": _TEST_PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    payload = jwt.decode(body["access_token"], options={"verify_signature": False}, algorithms=[_JWT_ALGORITHM])
    assert payload["sub"] == _TEST_USERNAME


def test_login_with_wrong_password_returns_401(staff_user):
    response = client.post("/auth/login", data={"username": _TEST_USERNAME, "password": "wrong"})
    assert response.status_code == 401


def test_login_with_unknown_username_returns_401():
    response = client.post("/auth/login", data={"username": "nobody", "password": "irrelevant"})
    assert response.status_code == 401


def test_delete_account_without_token_returns_401(account):
    response = client.delete(f"/accounts/{account}")
    assert response.status_code == 401


def test_delete_account_with_garbage_token_returns_401(account):
    response = client.delete(f"/accounts/{account}", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_delete_account_with_token_for_a_deleted_staff_user_returns_401(account):
    # Simulates a revoked/removed staff account - the token itself is
    # well-formed and unexpired, but re-fetching the user must still fail.
    token = create_access_token("someone-who-does-not-exist")
    response = client.delete(f"/accounts/{account}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_delete_account_with_valid_token_succeeds(staff_user, account):
    login = client.post("/auth/login", data={"username": _TEST_USERNAME, "password": _TEST_PASSWORD})
    token = login.json()["access_token"]
    response = client.delete(f"/accounts/{account}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert client.get(f"/accounts/{account}").status_code == 404
