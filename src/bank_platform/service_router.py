"""REST endpoints for the Service Requests domain. Deterministic, non-LLM
entry point into service_server.py. Create is nested under the owning
account (/accounts/{account_id}/service-requests); get/update/delete
address a request directly by its own id - no prefix is set on the router
so both path shapes can coexist here.

Every customer-facing endpoint requires a real customer
(Depends(get_current_customer)) and enforces ownership via authz.py -
added to close the gap where any anonymous caller could act on any
account_id/request_id it named (see account-schema-redesign-deferred
memory's 2026-09-12 update).

Status changes (approve/reject/complete) are staff-only - see
staff_update_service_request_status below. A customer's own PATCH can only
change `details`; letting a customer set their own request's `status` let
any customer self-approve their own request (e.g. change_of_address),
which is the gap this fixes.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from bank_platform import authz, service_server
from bank_platform.auth import get_current_customer, get_current_staff_user
from bank_platform.exceptions import NotFoundError
from bank_platform.models import Customer

router = APIRouter(tags=["service-requests"])


class ServiceRequestResponse(BaseModel):
    id: str
    account_id: str
    request_type: str
    status: str
    details: str | None


class CreateServiceRequestRequest(BaseModel):
    request_type: str
    details: str | None = None


class UpdateServiceRequestRequest(BaseModel):
    # No `status` field - customers can only change details. Status
    # transitions go through staff_update_service_request_status below.
    details: str | None = None


class StaffUpdateServiceRequestStatusRequest(BaseModel):
    status: str


def _require_owns_request(request_id: str, customer_id: str) -> None:
    account_id = service_server.get_service_request_account_id(request_id)
    if account_id is None:
        raise NotFoundError(f"Service request {request_id} not found")
    authz.require_owner(account_id, customer_id)


@router.post("/accounts/{account_id}/service-requests", response_model=ServiceRequestResponse, status_code=201)
async def create_service_request(
    account_id: str, body: CreateServiceRequestRequest, current_customer: Customer = Depends(get_current_customer)
):
    authz.require_owner(account_id, current_customer.id)
    return service_server.create_service_request(account_id, body.request_type, body.details)


@router.get("/service-requests/{request_id}", response_model=ServiceRequestResponse)
async def get_service_request(request_id: str, current_customer: Customer = Depends(get_current_customer)):
    _require_owns_request(request_id, current_customer.id)
    return service_server.get_service_request(request_id)


@router.patch("/service-requests/{request_id}", response_model=ServiceRequestResponse)
async def update_service_request(
    request_id: str, body: UpdateServiceRequestRequest, current_customer: Customer = Depends(get_current_customer)
):
    _require_owns_request(request_id, current_customer.id)
    return service_server.update_service_request(request_id, details=body.details)


@router.patch("/staff/service-requests/{request_id}/status", response_model=ServiceRequestResponse)
async def staff_update_service_request_status(
    request_id: str,
    body: StaffUpdateServiceRequestStatusRequest,
    _staff_user=Depends(get_current_staff_user),
):
    """Approve/reject/complete a service request. Staff-only - the state
    machine itself (service_server._ALLOWED_STATUS_TRANSITIONS) still
    enforces which transitions are legal; this endpoint only enforces who
    may trigger one."""
    return service_server.update_service_request(request_id, status=body.status)


@router.delete("/service-requests/{request_id}", response_model=ServiceRequestResponse)
async def delete_service_request(request_id: str, current_customer: Customer = Depends(get_current_customer)):
    _require_owns_request(request_id, current_customer.id)
    return service_server.delete_service_request(request_id)
