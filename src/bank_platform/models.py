import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Numeric
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_name: Mapped[str] = mapped_column(String(100))
    balance: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    # Nullable: added to an already-existing table via a manual ALTER TABLE
    # (no migration tool - see CLAUDE.md). Old/orphan rows have no owner and
    # are simply inaccessible via ownership-gated endpoints - correct, not a
    # bug. Doesn't touch owner_name itself - that redesign stays deferred,
    # see account-schema-redesign-deferred memory.
    customer_id: Mapped[str | None] = mapped_column(String, nullable=True)

class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(String)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    description: Mapped[str | None] = mapped_column(String, nullable=True)

class ServiceRequest(Base):
    __tablename__ = "service_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(String)
    request_type: Mapped[str] = mapped_column(String)
    details: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")

class StaffUser(Base):
    """Real staff/admin identity (Phase 6 - Auth & Authorisation),
    replacing admin_auth.py's static shared-secret gate. Deliberately
    minimal - no role field, since there is exactly one elevated action
    in the app today (deleting an account); a role/permission system
    would be speculative until a second one exists. Not linked to
    Account - staff aren't customers, and customer identity is a
    separate, deferred design (see PROGRESS.md Phase 6 / account-schema-
    redesign-deferred memory)."""
    __tablename__ = "staff_users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)

class Customer(Base):
    """Real customer login identity - added to close the gap where any
    anonymous caller could act on any account_id it named. Deliberately
    separate from StaffUser (different identity kind, different JWT "typ"
    claim) and NOT a redesign of Account.owner_name - that identity
    de-duplication question stays deferred (see account-schema-redesign-
    deferred memory). One customer can own many accounts (Account.customer_id)."""
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)

class Session(Base):
    """Inter-agent shared state store (Phase 4) - separate from conversation
    history, which lives in the LangGraph checkpointer's own tables. Nothing
    reads/writes this yet; see session_store.py."""
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

class AgentEventLog(Base):
    """Phase 8 (Observability & Cost Tracker) - one row per LLM call or
    tool call, written by observability.py's callback handler. Deliberately
    metadata only (tokens, timing, success/failure) - never raw prompt/
    reply/tool-arg content, which is where real account data lives and
    where Phase 5's PII tokenization already draws its own line. An
    append-only log, not a normalized schema - matches what this actually
    is."""
    __tablename__ = "agent_event_log"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    customer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    event_type: Mapped[str] = mapped_column(String)  # "llm_call" | "tool_call"
    # Best-effort only - not guaranteed populated, see observability.py.
    agent_name: Mapped[str | None] = mapped_column(String, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
