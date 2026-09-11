"""Service MCP server (in-process). Owns the ServiceRequest table and its
invariants: request_type allowlist, status transition state machine.
"""

import crud_service
from database import SessionLocal
from exceptions import InvalidStatusTransitionError, NotFoundError, ValidationError

_ALLOWED_REQUEST_TYPES = {"change_of_address", "cheque_book_request", "kyc_update"}

_ALLOWED_STATUS_TRANSITIONS = {
    "pending": {"approved", "rejected"},
    "approved": {"completed"},
    "rejected": set(),   # terminal
    "completed": set(),  # terminal
}


def _serialize(request) -> dict:
    return {
        "id": request.id,
        "account_id": request.account_id,
        "request_type": request.request_type,
        "status": request.status,
        "details": request.details,
    }


def create_service_request(account_id, request_type, details=None) -> dict:
    if request_type not in _ALLOWED_REQUEST_TYPES:
        raise ValidationError(f"'{request_type}' is not a valid request_type")

    session = SessionLocal()
    try:
        request = crud_service.create_service_request(session, account_id, request_type, details)
        session.commit()
        return _serialize(request)
    finally:
        session.close()


def get_service_request(id) -> dict:
    session = SessionLocal()
    try:
        request = crud_service.get_service_request(session, id)
        if request is None:
            raise NotFoundError(f"Service request {id} not found")
        return _serialize(request)
    finally:
        session.close()


def update_service_request(id, status=None, details=None) -> dict:
    session = SessionLocal()
    try:
        if status is not None:
            current = crud_service.get_service_request(session, id)
            if current is None:
                raise NotFoundError(f"Service request {id} not found")
            if status not in _ALLOWED_STATUS_TRANSITIONS:
                raise ValidationError(f"'{status}' is not a valid status")
            allowed_next = _ALLOWED_STATUS_TRANSITIONS[current.status]
            if status not in allowed_next:
                raise InvalidStatusTransitionError(
                    f"Cannot transition from '{current.status}' to '{status}'"
                )

        request = crud_service.update_service_request(session, id, status=status, details=details)
        if request is None:
            raise NotFoundError(f"Service request {id} not found")
        session.commit()
        return _serialize(request)
    finally:
        session.close()


def delete_service_request(id) -> dict:
    session = SessionLocal()
    try:
        request = crud_service.delete_service_request(session, id)
        if request is None:
            raise NotFoundError(f"Service request {id} not found")
        session.commit()
        return _serialize(request)
    finally:
        session.close()
