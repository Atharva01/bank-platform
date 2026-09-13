import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from bank_platform import (
    accounts_router,
    auth_router,
    customer_router,
    observability_router,
    service_router,
    transactions_router,
)
from bank_platform.auth import get_current_customer
from bank_platform.exceptions import (
    InsufficientFundsError,
    InvalidStatusTransitionError,
    NotFoundError,
    SessionOwnershipError,
    ValidationError,
)
from bank_platform.graph import SESSION_IDLE_TIMEOUT, run, sweep_expired_sessions
from bank_platform.models import Customer
from bank_platform.rate_limit import limiter

logger = logging.getLogger(__name__)

# Runs sweep_expired_sessions() on a timer so an abandoned session (one
# that's never messaged again) still gets cleaned up, not just sessions
# still receiving traffic (graph.py's per-request _expire_if_idle only
# catches those). No scheduler dependency needed - a background asyncio
# task under FastAPI's lifespan is enough for one lightweight periodic job.
# Interval matches the idle timeout itself: no point sweeping more often
# than sessions can actually go stale.
_SWEEP_INTERVAL = SESSION_IDLE_TIMEOUT.total_seconds()


async def _sweep_loop() -> None:
    while True:
        await asyncio.sleep(_SWEEP_INTERVAL)
        try:
            cleaned = sweep_expired_sessions()
            if cleaned:
                logger.info("session sweep: cleaned up %d expired session(s)", cleaned)
        except Exception:
            logger.exception("session sweep failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_sweep_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(lifespan=lifespan)

# Phase 7 - Edge Layer: in-app rate limiting (slowapi). See rate_limit.py
# for the shared Limiter instance and its in-memory-storage caveat.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Phase 7 - Edge Layer: same-origin in production once Traefik mounts the
# backend under /api on the same domain as the frontend (see
# docker-compose.prod.yml) - CORS headers become unnecessary there, but
# local dev still needs them (frontend dev server on a different port
# than the backend), so this stays configurable rather than removed.
# Defaults to the old permissive value so local dev is unaffected.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_ORIGIN", "*")],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase 7 - Edge Layer: every backend route lives under /api so Traefik
# can route the whole domain to the frontend except this one path prefix
# (Host(domain) && PathPrefix(/api)), matching FastAPI's own reference
# deployment architecture (full-stack-fastapi-template) - same-origin by
# construction, no CORS to get wrong in production. Each router's own
# internal prefix (e.g. accounts_router's "/accounts") is untouched; only
# nested one level deeper here.
api_router = APIRouter(prefix="/api")
api_router.include_router(accounts_router.router)
api_router.include_router(transactions_router.router)
api_router.include_router(service_router.router)
api_router.include_router(auth_router.router)
api_router.include_router(customer_router.router)
api_router.include_router(observability_router.router)

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
    # Unlike the four above (REST-only, /chat's failures are otherwise
    # communicated conversationally by the LLM), this one also applies to
    # /chat: a session_id reused by a different customer is an auth-layer
    # problem, not something the LLM should try to explain away.
    SessionOwnershipError: 403,
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


@api_router.post("/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat(
    request: Request, chat_request: ChatRequest, current_customer: Customer = Depends(get_current_customer)
):
    reply = run(chat_request.message, chat_request.session_id, current_customer.id)
    return ChatResponse(reply=reply)


app.include_router(api_router)
