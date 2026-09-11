from agents import AccountsAgent, AgentRequest, ServiceAgent
from database import SessionLocal
from models import Account

accounts_agent = AccountsAgent()
service_agent = ServiceAgent()


def _delete_account(account_id):
    session = SessionLocal()
    try:
        obj = session.get(Account, account_id)
        if obj is not None:
            session.delete(obj)
            session.commit()
    finally:
        session.close()


def _open_account():
    created = accounts_agent.handle(AgentRequest(
        session_id="s1", user_query="open account", intent="accounts.create",
        payload={"owner_name": "Status Test", "balance": 0},
    ))
    return created.data["id"]


def _open_request(account_id):
    created = service_agent.handle(AgentRequest(
        session_id="s1", user_query="request", intent="service.create",
        payload={"account_id": account_id, "request_type": "change_of_address", "details": "x"},
    ))
    assert created.success is True
    return created.data["id"]


def test_pending_to_approved_is_allowed():
    account_id = _open_account()
    try:
        request_id = _open_request(account_id)
        response = service_agent.handle(AgentRequest(
            session_id="s1", user_query="approve", intent="service.update",
            payload={"id": request_id, "status": "approved"},
        ))
        assert response.success is True
        assert response.data["status"] == "approved"
    finally:
        _delete_account(account_id)


def test_pending_to_rejected_is_allowed():
    account_id = _open_account()
    try:
        request_id = _open_request(account_id)
        response = service_agent.handle(AgentRequest(
            session_id="s1", user_query="reject", intent="service.update",
            payload={"id": request_id, "status": "rejected"},
        ))
        assert response.success is True
        assert response.data["status"] == "rejected"
    finally:
        _delete_account(account_id)


def test_approved_to_completed_is_allowed():
    account_id = _open_account()
    try:
        request_id = _open_request(account_id)
        service_agent.handle(AgentRequest(
            session_id="s1", user_query="approve", intent="service.update",
            payload={"id": request_id, "status": "approved"},
        ))
        response = service_agent.handle(AgentRequest(
            session_id="s1", user_query="complete", intent="service.update",
            payload={"id": request_id, "status": "completed"},
        ))
        assert response.success is True
        assert response.data["status"] == "completed"
    finally:
        _delete_account(account_id)


def test_pending_to_completed_is_rejected():
    account_id = _open_account()
    try:
        request_id = _open_request(account_id)
        response = service_agent.handle(AgentRequest(
            session_id="s1", user_query="skip ahead", intent="service.update",
            payload={"id": request_id, "status": "completed"},
        ))
        assert response.success is False
        assert response.error == "invalid_status_transition"
    finally:
        _delete_account(account_id)


def test_terminal_status_cannot_transition_again():
    account_id = _open_account()
    try:
        request_id = _open_request(account_id)
        service_agent.handle(AgentRequest(
            session_id="s1", user_query="reject", intent="service.update",
            payload={"id": request_id, "status": "rejected"},
        ))
        response = service_agent.handle(AgentRequest(
            session_id="s1", user_query="reopen", intent="service.update",
            payload={"id": request_id, "status": "pending"},
        ))
        assert response.success is False
        assert response.error == "invalid_status_transition"
    finally:
        _delete_account(account_id)


def test_unknown_status_value_is_a_validation_error():
    account_id = _open_account()
    try:
        request_id = _open_request(account_id)
        response = service_agent.handle(AgentRequest(
            session_id="s1", user_query="bogus", intent="service.update",
            payload={"id": request_id, "status": "archived"},
        ))
        assert response.success is False
        assert response.error == "validation_error"
    finally:
        _delete_account(account_id)


def test_details_only_update_does_not_require_status():
    account_id = _open_account()
    try:
        request_id = _open_request(account_id)
        response = service_agent.handle(AgentRequest(
            session_id="s1", user_query="add note", intent="service.update",
            payload={"id": request_id, "details": "updated note"},
        ))
        assert response.success is True
        assert response.data["status"] == "pending"
        assert response.data["details"] == "updated note"
    finally:
        _delete_account(account_id)
