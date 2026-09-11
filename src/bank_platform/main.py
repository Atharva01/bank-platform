import asyncio
import logging
from contextlib import asynccontextmanager

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
from bank_platform.graph import SESSION_IDLE_TIMEOUT, run, sweep_expired_sessions

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
