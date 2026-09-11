from bank_platform.agents import AccountsAgent, AgentRequest, ServiceAgent
from bank_platform.database import SessionLocal
from bank_platform.models import Account

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


def test_negative_balance_on_create_is_rejected():
    response = accounts_agent.handle(AgentRequest(
        session_id="s1", user_query="open account", intent="accounts.create",
        payload={"owner_name": "Bad Balance", "balance": -10},
    ))
    assert response.success is False
    assert response.error == "validation_error"


def test_empty_owner_name_on_create_is_rejected():
    response = accounts_agent.handle(AgentRequest(
        session_id="s1", user_query="open account", intent="accounts.create",
        payload={"owner_name": "   ", "balance": 0},
    ))
    assert response.success is False
    assert response.error == "validation_error"


def test_negative_balance_on_update_is_rejected():
    created = accounts_agent.handle(AgentRequest(
        session_id="s1", user_query="open account", intent="accounts.create",
        payload={"owner_name": "Update Test", "balance": 50},
    ))
    account_id = created.data["id"]
    try:
        response = accounts_agent.handle(AgentRequest(
            session_id="s1", user_query="edit", intent="accounts.update",
            payload={"id": account_id, "balance": -5},
        ))
        assert response.success is False
        assert response.error == "validation_error"
    finally:
        _delete_account(account_id)


def test_empty_owner_name_on_update_is_rejected():
    created = accounts_agent.handle(AgentRequest(
        session_id="s1", user_query="open account", intent="accounts.create",
        payload={"owner_name": "Update Test", "balance": 50},
    ))
    account_id = created.data["id"]
    try:
        response = accounts_agent.handle(AgentRequest(
            session_id="s1", user_query="edit", intent="accounts.update",
            payload={"id": account_id, "owner_name": ""},
        ))
        assert response.success is False
        assert response.error == "validation_error"
    finally:
        _delete_account(account_id)


def test_valid_balance_update_still_works():
    created = accounts_agent.handle(AgentRequest(
        session_id="s1", user_query="open account", intent="accounts.create",
        payload={"owner_name": "Update Test", "balance": 50},
    ))
    account_id = created.data["id"]
    try:
        response = accounts_agent.handle(AgentRequest(
            session_id="s1", user_query="edit", intent="accounts.update",
            payload={"id": account_id, "balance": 200},
        ))
        assert response.success is True
        assert response.data["balance"] == 200
    finally:
        _delete_account(account_id)


def test_unknown_request_type_on_service_create_is_rejected():
    created = accounts_agent.handle(AgentRequest(
        session_id="s1", user_query="open account", intent="accounts.create",
        payload={"owner_name": "Service Validation", "balance": 0},
    ))
    account_id = created.data["id"]
    try:
        response = service_agent.handle(AgentRequest(
            session_id="s1", user_query="bogus request", intent="service.create",
            payload={"account_id": account_id, "request_type": "loan_application"},
        ))
        assert response.success is False
        assert response.error == "validation_error"
    finally:
        _delete_account(account_id)


def test_known_request_types_are_accepted():
    created = accounts_agent.handle(AgentRequest(
        session_id="s1", user_query="open account", intent="accounts.create",
        payload={"owner_name": "Service Validation", "balance": 0},
    ))
    account_id = created.data["id"]
    try:
        for request_type in ("change_of_address", "cheque_book_request", "kyc_update"):
            response = service_agent.handle(AgentRequest(
                session_id="s1", user_query="request", intent="service.create",
                payload={"account_id": account_id, "request_type": request_type},
            ))
            assert response.success is True, request_type
    finally:
        _delete_account(account_id)
