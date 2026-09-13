import uuid

import pytest
from fastapi.testclient import TestClient

from bank_platform.auth import create_access_token, hash_password
from bank_platform.database import SessionLocal
from bank_platform.main import app
from bank_platform.models import Customer
from bank_platform.rate_limit import limiter

client = TestClient(app)


@pytest.fixture
def customer_token():
    username = f"rate-limit-test-{uuid.uuid4().hex[:8]}"
    user_id = str(uuid.uuid4())
    db = SessionLocal()
    db.add(Customer(id=user_id, username=username, hashed_password=hash_password("irrelevant")))
    db.commit()
    db.close()
    yield create_access_token(username, "customer")
    db = SessionLocal()
    row = db.get(Customer, user_id)
    if row is not None:
        db.delete(row)
        db.commit()
    db.close()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    # The Limiter is a module-level singleton shared with every other test
    # file that hits /api/auth/login (test_auth.py). Reset before each test in
    # this file so those unrelated calls never count toward the limits
    # being tested here, and so the two tests below don't interfere with
    # each other.
    limiter.reset()
    yield


def test_login_is_rate_limited_after_five_per_minute():
    for _ in range(5):
        response = client.post("/api/auth/login", data={"username": "nobody", "password": "wrong"})
        assert response.status_code == 401

    response = client.post("/api/auth/login", data={"username": "nobody", "password": "wrong"})
    assert response.status_code == 429


def test_chat_is_rate_limited_after_twenty_per_minute(monkeypatch, customer_token):
    # Stubs out the actual LLM call - this test is about the rate-limit
    # decorator firing on the 21st request, not about /chat's real
    # behavior, and running 21 live LLM calls here would be exactly the
    # kind of mindless endpoint hammering the project avoids.
    monkeypatch.setattr("bank_platform.main.run", lambda message, session_id, customer_id: "stub reply")
    headers = {"Authorization": f"Bearer {customer_token}"}

    for i in range(20):
        response = client.post(
            "/api/chat", json={"session_id": "rate-limit-test", "message": f"hi {i}"}, headers=headers
        )
        assert response.status_code == 200

    response = client.post(
        "/api/chat", json={"session_id": "rate-limit-test", "message": "one too many"}, headers=headers
    )
    assert response.status_code == 429
