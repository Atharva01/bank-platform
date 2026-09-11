from sqlalchemy import update
from sqlalchemy.orm import Session

from models import ServiceRequest


def create_service_request(
    session: Session, account_id: str, request_type: str, details: str | None = None
):
    service_request = ServiceRequest(
        account_id=account_id, request_type=request_type, details=details
    )
    session.add(service_request)
    session.flush()
    return service_request


def get_service_request(session: Session, request_id: str):
    return session.get(ServiceRequest, request_id)


def update_service_request(
    session: Session,
    request_id: str,
    status: str | None = None,
    details: str | None = None,
):
    update_data = {}

    if isinstance(status, str):
        update_data["status"] = status

    if isinstance(details, str):
        update_data["details"] = details

    if update_data:
        statement = (
            update(ServiceRequest).where(ServiceRequest.id == request_id).values(**update_data)
        )
        session.execute(statement)
        session.flush()

    return get_service_request(session, request_id)


def delete_service_request(session: Session, request_id: str):
    service_request = session.get(ServiceRequest, request_id)
    if service_request is None:
        return None

    session.delete(service_request)
    session.flush()

    return service_request
