"""Postgres-backed implementation of interfaces.py's SessionStore ABC -
"inter-agent shared state", the second Session Store responsibility from
the architecture diagram. Separate from conversation history, which lives
in the LangGraph checkpointer's own tables (see graph.py).

First real consumer: graph.py's session/customer binding check (added at
explicit user direction - see account-schema-redesign-deferred memory's
2026-09-12 update), via the module-level `store` instance below.
"""

from datetime import datetime, timezone

from sqlalchemy import select

from bank_platform.database import SessionLocal
from bank_platform.interfaces import SessionStore
from bank_platform.models import Session


class PostgresSessionStore(SessionStore):
    def get(self, session_id: str) -> dict:
        """Returns the session's shared-state dict, or {} if it has none yet."""
        session = SessionLocal()
        try:
            row = session.get(Session, session_id)
            return dict(row.data) if row is not None else {}
        finally:
            session.close()

    def update(self, session_id: str, data: dict) -> None:
        """Merges `data` into the session's existing shared state (not a
        wholesale replace) - multiple agents writing different keys
        shouldn't clobber each other's fields. Creates the session row if
        it doesn't exist yet."""
        db = SessionLocal()
        try:
            row = db.get(Session, session_id)
            if row is None:
                db.add(Session(session_id=session_id, data=dict(data)))
            else:
                merged = dict(row.data)
                merged.update(data)
                row.data = merged
            db.commit()
        finally:
            db.close()


store = PostgresSessionStore()


def touch(session_id: str) -> None:
    """Bumps a session's updated_at to now without touching its shared-state
    data - graph.py calls this once per /chat request to record activity,
    which is what the idle-expiry check in graph.py reads. Deliberately
    separate from update() so "record activity" and "write shared state"
    stay distinct operations."""
    db = SessionLocal()
    try:
        row = db.get(Session, session_id)
        if row is None:
            db.add(Session(session_id=session_id, data={}))
        else:
            row.updated_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def get_last_activity(session_id: str) -> datetime | None:
    """Returns the session's updated_at, or None if it has no row yet
    (i.e. it has never been active - not expired, just new)."""
    db = SessionLocal()
    try:
        row = db.get(Session, session_id)
        return row.updated_at if row is not None else None
    finally:
        db.close()


def list_expired_session_ids(cutoff: datetime) -> list[str]:
    """Session ids whose last activity is older than `cutoff` - the query
    graph.py's periodic sweep needs to find abandoned sessions in bulk,
    instead of the per-request expiry check which only ever looks at the
    one session being used right now."""
    db = SessionLocal()
    try:
        statement = select(Session.session_id).where(Session.updated_at < cutoff)
        return list(db.execute(statement).scalars().all())
    finally:
        db.close()


def delete(session_id: str) -> None:
    """Removes a session's shared-state row - called alongside checkpoint
    and idempotency-dict cleanup when a session is found to have expired."""
    db = SessionLocal()
    try:
        row = db.get(Session, session_id)
        if row is not None:
            db.delete(row)
            db.commit()
    finally:
        db.close()
