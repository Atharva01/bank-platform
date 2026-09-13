import uuid

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from bank_platform.auth import _JWT_ALGORITHM, create_access_token, hash_password
from bank_platform.database import SessionLocal
from bank_platform.main import app
from bank_platform.models import Customer
from bank_platform.rate_limit import limiter

client = TestClient(app)

_TEST_USERNAME = "test-customer"
_TEST_PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    # /api/customers/register and /api/customers/login are rate-limited (5/min,
    # same as /api/auth/login) - reset so this file's own repeated calls never
    # collide with each other or with test_rate_limiting.py.
    limiter.reset()
    yield


@pytest.fixture
def customer_user():
    db = SessionLocal()
    user = Customer(id=str(uuid.uuid4()), username=_TEST_USERNAME, hashed_password=hash_password(_TEST_PASSWORD))
    db.add(user)
    db.commit()
    db.close()
    yield
    db = SessionLocal()
    row = db.execute(select(Customer).where(Customer.username == _TEST_USERNAME)).scalar_one_or_none()
    if row is not None:
        db.delete(row)
        db.commit()
    db.close()


def _delete_customer_by_username(username: str) -> None:
    db = SessionLocal()
    row = db.execute(select(Customer).where(Customer.username == username)).scalar_one_or_none()
    if row is not None:
        db.delete(row)
        db.commit()
    db.close()


def test_register_creates_a_customer_and_returns_a_token():
    username = f"register-test-{uuid.uuid4().hex[:8]}"
    try:
        response = client.post("/api/customers/register", json={"username": username, "password": "a-real-password"})
        assert response.status_code == 201
        body = response.json()
        assert body["token_type"] == "bearer"
        payload = jwt.decode(body["access_token"], options={"verify_signature": False}, algorithms=[_JWT_ALGORITHM])
        assert payload["sub"] == username
        assert payload["typ"] == "customer"
    finally:
        _delete_customer_by_username(username)


def test_register_rejects_a_short_password():
    response = client.post(
        "/api/customers/register", json={"username": f"short-pw-{uuid.uuid4().hex[:8]}", "password": "short"}
    )
    assert response.status_code == 400


def test_register_rejects_a_duplicate_username(customer_user):
    response = client.post("/api/customers/register", json={"username": _TEST_USERNAME, "password": "irrelevant123"})
    assert response.status_code == 409


def test_login_with_correct_credentials_returns_a_token(customer_user):
    response = client.post("/api/customers/login", data={"username": _TEST_USERNAME, "password": _TEST_PASSWORD})
    assert response.status_code == 200
    payload = jwt.decode(
        response.json()["access_token"], options={"verify_signature": False}, algorithms=[_JWT_ALGORITHM]
    )
    assert payload["typ"] == "customer"


def test_login_with_wrong_password_returns_401(customer_user):
    response = client.post("/api/customers/login", data={"username": _TEST_USERNAME, "password": "wrong"})
    assert response.status_code == 401


def test_login_with_unknown_username_returns_401():
    response = client.post("/api/customers/login", data={"username": "nobody", "password": "irrelevant"})
    assert response.status_code == 401


def test_a_staff_token_cannot_pass_as_a_customer_token(customer_user):
    # Mirrors test_auth.py's identical check in the other direction - a
    # staff and a customer JWT must be structurally distinguishable.
    staff_style_token = create_access_token(_TEST_USERNAME, "staff")
    response = client.post(
        "/api/chat",
        json={"session_id": "whatever", "message": "hi"},
        headers={"Authorization": f"Bearer {staff_style_token}"},
    )
    assert response.status_code == 401
