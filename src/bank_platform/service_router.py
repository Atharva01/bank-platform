"""REST endpoints for the Service Requests domain. Deterministic, non-LLM
entry point into service_server.py. Create is nested under the owning
account (/accounts/{account_id}/service-requests); get/update/delete
address a request directly by its own id - no prefix is set on the router
so both path shapes can coexist here.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from bank_platform import service_server

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
    status: str | None = None
    details: str | None = None


@router.post("/accounts/{account_id}/service-requests", response_model=ServiceRequestResponse, status_code=201)
async def create_service_request(account_id: str, body: CreateServiceRequestRequest):
    return service_server.create_service_request(account_id, body.request_type, body.details)


@router.get("/service-requests/{request_id}", response_model=ServiceRequestResponse)
async def get_service_request(request_id: str):
    return service_server.get_service_request(request_id)


@router.patch("/service-requests/{request_id}", response_model=ServiceRequestResponse)
async def update_service_request(request_id: str, body: UpdateServiceRequestRequest):
    return service_server.update_service_request(request_id, status=body.status, details=body.details)


@router.delete("/service-requests/{request_id}", response_model=ServiceRequestResponse)
async def delete_service_request(request_id: str):
    return service_server.delete_service_request(request_id)
