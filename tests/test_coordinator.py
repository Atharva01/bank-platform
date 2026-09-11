from bank_platform.agents import AgentRequest
from bank_platform.coordinator import Coordinator

coordinator = Coordinator()


def test_missing_intent_returns_invalid_intent_error():
    response = coordinator.route(AgentRequest(session_id="s1", user_query="x", intent=None))
    assert response.success is False
    assert response.error == "invalid_intent"


def test_unknown_agent_returns_unknown_agent_error():
    response = coordinator.route(
        AgentRequest(session_id="s1", user_query="x", intent="bogus.create")
    )
    assert response.success is False
    assert response.error == "unknown_agent"
