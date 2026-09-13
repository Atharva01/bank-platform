"""Zero-LLM-call tests for observability.py's callback handler (Phase 8 -
Observability & Cost Tracker). Feeds it synthetic LangChain objects
directly - the same "verify the mechanism, not a live model" approach
test_pii_guard.py uses.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from bank_platform.auth import create_access_token, hash_password
from bank_platform.database import SessionLocal
from bank_platform.main import app
from bank_platform.models import AgentEventLog, StaffUser
from bank_platform.observability import ObservabilityCallbackHandler, _estimate_cost

client = TestClient(app)


def _cleanup(session_id):
    db = SessionLocal()
    db.query(AgentEventLog).filter(AgentEventLog.session_id == session_id).delete()
    db.commit()
    db.close()


def test_estimate_cost_uses_the_known_model_rate():
    cost = _estimate_cost("openai/gpt-oss-20b", 1_000_000, 1_000_000)
    assert cost == 0.075 + 0.30


def test_estimate_cost_is_none_for_an_unknown_model():
    assert _estimate_cost("muse-spark-1.3-contributor", 100, 50) is None


def test_estimate_cost_is_none_without_a_model():
    assert _estimate_cost(None, 100, 50) is None


def test_llm_call_records_tokens_and_cost():
    session_id = f"obs-test-{uuid.uuid4().hex[:8]}"
    handler = ObservabilityCallbackHandler()
    run_id = uuid.uuid4()

    handler.on_chat_model_start(
        serialized={"kwargs": {"model": "openai/gpt-oss-20b"}},
        messages=[],
        run_id=run_id,
        metadata={"thread_id": session_id, "customer_id": "cust-1"},
    )
    message = AIMessage(content="hi", usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150})
    handler.on_llm_end(LLMResult(generations=[[ChatGeneration(message=message)]]), run_id=run_id)

    db = SessionLocal()
    try:
        row = db.query(AgentEventLog).filter(AgentEventLog.session_id == session_id).one()
        assert row.event_type == "llm_call"
        assert row.customer_id == "cust-1"
        assert row.prompt_tokens == 100
        assert row.completion_tokens == 50
        assert row.total_tokens == 150
        assert row.estimated_cost_usd is not None
        assert row.success is True
    finally:
        db.close()
        _cleanup(session_id)


def test_llm_error_records_failure_without_tokens():
    session_id = f"obs-test-{uuid.uuid4().hex[:8]}"
    handler = ObservabilityCallbackHandler()
    run_id = uuid.uuid4()

    handler.on_chat_model_start(
        serialized={"kwargs": {"model": "openai/gpt-oss-20b"}},
        messages=[],
        run_id=run_id,
        metadata={"thread_id": session_id, "customer_id": "cust-1"},
    )
    handler.on_llm_error(RuntimeError("boom"), run_id=run_id)

    db = SessionLocal()
    try:
        row = db.query(AgentEventLog).filter(AgentEventLog.session_id == session_id).one()
        assert row.success is False
        assert "boom" in row.error_message
        assert row.total_tokens is None
    finally:
        db.close()
        _cleanup(session_id)


def test_tool_call_records_the_tool_name():
    # Regression-relevant: `metadata` is verified NOT to reach *_end
    # callbacks (only *_start) - this confirms context captured at start
    # (tool name included) survives through to the row written at end.
    session_id = f"obs-test-{uuid.uuid4().hex[:8]}"
    handler = ObservabilityCallbackHandler()
    run_id = uuid.uuid4()

    handler.on_tool_start(
        serialized={"name": "get_account"},
        input_str="{}",
        run_id=run_id,
        metadata={"thread_id": session_id, "customer_id": "cust-1"},
    )
    handler.on_tool_end(output="result", run_id=run_id)

    db = SessionLocal()
    try:
        row = db.query(AgentEventLog).filter(AgentEventLog.session_id == session_id).one()
        assert row.event_type == "tool_call"
        assert row.tool_name == "get_account"
        assert row.success is True
    finally:
        db.close()
        _cleanup(session_id)


def test_tool_error_records_failure():
    session_id = f"obs-test-{uuid.uuid4().hex[:8]}"
    handler = ObservabilityCallbackHandler()
    run_id = uuid.uuid4()

    handler.on_tool_start(
        serialized={"name": "get_account"},
        input_str="{}",
        run_id=run_id,
        metadata={"thread_id": session_id, "customer_id": "cust-1"},
    )
    handler.on_tool_error(RuntimeError("tool broke"), run_id=run_id)

    db = SessionLocal()
    try:
        row = db.query(AgentEventLog).filter(AgentEventLog.session_id == session_id).one()
        assert row.success is False
        assert "tool broke" in row.error_message
    finally:
        db.close()
        _cleanup(session_id)


def test_unknown_run_id_does_not_crash():
    # *_end called without a matching *_start (shouldn't happen in
    # practice, but the handler must not crash a real chat request over it).
    handler = ObservabilityCallbackHandler()
    handler.on_tool_end(output="result", run_id=uuid.uuid4())

    db = SessionLocal()
    db.query(AgentEventLog).filter(AgentEventLog.session_id.is_(None)).delete()
    db.commit()
    db.close()


# --- GET /observability/usage (REST) ---


@pytest.fixture
def staff_token():
    username = f"obs-test-staff-{uuid.uuid4().hex[:8]}"
    user_id = str(uuid.uuid4())
    db = SessionLocal()
    db.add(StaffUser(id=user_id, username=username, hashed_password=hash_password("irrelevant")))
    db.commit()
    db.close()
    yield create_access_token(username, "staff")
    db = SessionLocal()
    row = db.get(StaffUser, user_id)
    if row is not None:
        db.delete(row)
        db.commit()
    db.close()


@pytest.fixture
def seeded_events():
    session_id = f"obs-usage-test-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    db.add(
        AgentEventLog(
            id=str(uuid.uuid4()),
            session_id=session_id,
            event_type="llm_call",
            duration_ms=100,
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            estimated_cost_usd=0.001,
            success=True,
        )
    )
    db.add(
        AgentEventLog(
            id=str(uuid.uuid4()),
            session_id=session_id,
            event_type="tool_call",
            tool_name="get_account",
            duration_ms=20,
            success=True,
        )
    )
    db.commit()
    db.close()
    yield session_id
    _cleanup(session_id)


def test_usage_endpoint_requires_staff_token(seeded_events):
    response = client.get("/observability/usage")
    assert response.status_code == 401


def test_usage_endpoint_reports_seeded_totals(seeded_events, staff_token):
    response = client.get("/observability/usage", headers={"Authorization": f"Bearer {staff_token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["totals"]["llm_calls"] >= 1
    assert body["totals"]["tool_calls"] >= 1
    assert body["totals"]["total_tokens"] >= 15
