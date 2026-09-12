import uuid

import pytest
from langchain_core.tools import StructuredTool

from bank_platform import accounts_server
from bank_platform.authz import owner_guard
from bank_platform.database import SessionLocal
from bank_platform.models import Account


def _delete_account(account_id):
    session = SessionLocal()
    try:
        obj = session.get(Account, account_id)
        if obj is not None:
            session.delete(obj)
            session.commit()
    finally:
        session.close()


@pytest.fixture
def account():
    result = accounts_server.create_account(owner_name="Authz Test", balance=10, customer_id="owner-1")
    yield result["id"]
    _delete_account(result["id"])


def test_owner_guard_allows_the_real_owner(account):
    wrapped = owner_guard(accounts_server.get_account, resolve_account_id=lambda kwargs: kwargs.get("id"))
    result = wrapped(id=account, config={"configurable": {"customer_id": "owner-1"}})
    assert result["id"] == account


def test_owner_guard_denies_a_different_customer(account):
    from langchain_core.tools import ToolException

    wrapped = owner_guard(accounts_server.get_account, resolve_account_id=lambda kwargs: kwargs.get("id"))
    with pytest.raises(ToolException):
        wrapped(id=account, config={"configurable": {"customer_id": "someone-else"}})


def test_owner_guard_denial_is_a_tool_exception_not_a_raw_domain_error():
    # Regression test: found live via a real /chat call - require_owner()
    # raising a bare NotFoundError from inside owner_guard (which runs
    # OUTSIDE tool_safe's own try/except) propagated past handle_tool_error
    # and surfaced as a raw HTTP 404 from /chat instead of a message the
    # LLM could react to. owner_guard must convert it to ToolException
    # itself.
    from langchain_core.tools import ToolException

    wrapped = owner_guard(accounts_server.get_account, resolve_account_id=lambda kwargs: kwargs.get("id"))
    with pytest.raises(ToolException):
        wrapped(id=str(uuid.uuid4()), config={"configurable": {"customer_id": "owner-1"}})


def test_owner_guard_denial_reaches_the_llm_as_a_tool_message_not_a_crash(account):
    # End-to-end through StructuredTool.invoke(), the same call path
    # LangChain's agent loop actually uses - confirms handle_tool_error
    # catches the ToolException and turns it into a normal tool result,
    # instead of an exception escaping the tool call entirely.
    tool = StructuredTool.from_function(
        func=owner_guard(accounts_server.get_account, resolve_account_id=lambda kwargs: kwargs.get("id")),
        handle_tool_error=True,
    )
    result = tool.invoke({"id": account}, config={"configurable": {"customer_id": "someone-else"}})
    assert "not found" in result.lower()
