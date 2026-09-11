import pytest

from bank_platform import accounts_server, service_server
from bank_platform.database import SessionLocal
from bank_platform.exceptions import InvalidStatusTransitionError, ValidationError
from bank_platform.models import Account


def _delete_account(account_id):
    session = SessionLocal()
    try:
        obj = session.get(Account, account_id)
        if obj is not None:
            session.delete(obj)
            session.commit()
    finally:
        session.close()


def _open_account():
    return accounts_server.create_account(owner_name="Status Test", balance=0)["id"]


def _open_request(account_id):
    return service_server.create_service_request(account_id, "change_of_address", "x")["id"]


def test_pending_to_approved_is_allowed():
    account_id = _open_account()
    try:
        request_id = _open_request(account_id)
        response = service_server.update_service_request(request_id, status="approved")
        assert response["status"] == "approved"
    finally:
        _delete_account(account_id)


def test_pending_to_rejected_is_allowed():
    account_id = _open_account()
    try:
        request_id = _open_request(account_id)
        response = service_server.update_service_request(request_id, status="rejected")
        assert response["status"] == "rejected"
    finally:
        _delete_account(account_id)


def test_approved_to_completed_is_allowed():
    account_id = _open_account()
    try:
        request_id = _open_request(account_id)
        service_server.update_service_request(request_id, status="approved")
        response = service_server.update_service_request(request_id, status="completed")
        assert response["status"] == "completed"
    finally:
        _delete_account(account_id)


def test_pending_to_completed_is_rejected():
    account_id = _open_account()
    try:
        request_id = _open_request(account_id)
        with pytest.raises(InvalidStatusTransitionError):
            service_server.update_service_request(request_id, status="completed")
    finally:
        _delete_account(account_id)


def test_terminal_status_cannot_transition_again():
    account_id = _open_account()
    try:
        request_id = _open_request(account_id)
        service_server.update_service_request(request_id, status="rejected")
        with pytest.raises(InvalidStatusTransitionError):
            service_server.update_service_request(request_id, status="pending")
    finally:
        _delete_account(account_id)


def test_unknown_status_value_is_a_validation_error():
    account_id = _open_account()
    try:
        request_id = _open_request(account_id)
        with pytest.raises(ValidationError):
            service_server.update_service_request(request_id, status="archived")
    finally:
        _delete_account(account_id)


def test_details_only_update_does_not_require_status():
    account_id = _open_account()
    try:
        request_id = _open_request(account_id)
        response = service_server.update_service_request(request_id, details="updated note")
        assert response["status"] == "pending"
        assert response["details"] == "updated note"
    finally:
        _delete_account(account_id)
