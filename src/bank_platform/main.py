from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from bank_platform import accounts_router, service_router, transactions_router
from bank_platform.exceptions import (
    InsufficientFundsError,
    InvalidStatusTransitionError,
    NotFoundError,
    ValidationError,
)
from bank_platform.graph import run

app = FastAPI()

# Dev-permissive for now — no frontend origin decided yet. Tighten
# allow_origins to specific hosts before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(accounts_router.router)
app.include_router(transactions_router.router)
app.include_router(service_router.router)

# Maps the business-layer exception taxonomy (exceptions.py) to real HTTP
# status codes for the REST endpoints. /chat is intentionally exempt - its
# failures are communicated conversationally by the LLM inside `reply`,
# which is the expected shape for a chat endpoint, not a gap being fixed
# here. `error_type` lets a caller branch on failure kind without
# string-matching `detail`.
_ERROR_STATUS = {
    NotFoundError: 404,
    ValidationError: 400,
    InvalidStatusTransitionError: 409,
    InsufficientFundsError: 422,
}


def _domain_error_handler(request: Request, exc: Exception):
    status_code = _ERROR_STATUS[type(exc)]
    return JSONResponse(status_code=status_code, content={"detail": str(exc), "error_type": type(exc).__name__})


for _exc_type in _ERROR_STATUS:
    app.add_exception_handler(_exc_type, _domain_error_handler)


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/")
async def home():
    return {"message": "Welcome home!"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    reply = run(request.message, request.session_id)
    return ChatResponse(reply=reply)
