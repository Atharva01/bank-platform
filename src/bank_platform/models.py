import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, String, Numeric
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_name: Mapped[str] = mapped_column(String(100))
    balance: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

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
