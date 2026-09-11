from datetime import datetime, timedelta, timezone

from bank_platform import session_store
from bank_platform.graph import sweep_expired_sessions


def test_sweep_removes_only_expired_sessions():
    session_store.touch("sweep-test-fresh")
    session_store.touch("sweep-test-stale")

    db = session_store.SessionLocal()
    try:
        row = db.get(session_store.Session, "sweep-test-stale")
        row.updated_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
    finally:
        db.close()

    cleaned = sweep_expired_sessions()

    assert cleaned >= 1
    assert session_store.get_last_activity("sweep-test-stale") is None
    assert session_store.get_last_activity("sweep-test-fresh") is not None

    session_store.delete("sweep-test-fresh")
