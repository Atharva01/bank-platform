import pytest

from bank_platform.agents import _operation


def test_valid_operation_is_returned():
    assert _operation("accounts.create") == "create"
    assert _operation("transaction.list") == "list"


def test_missing_intent_raises():
    with pytest.raises(ValueError):
        _operation(None)


def test_intent_without_dot_raises():
    with pytest.raises(ValueError):
        _operation("accounts")


def test_operation_not_allowed_for_agent_raises():
    with pytest.raises(ValueError):
        _operation("accounts.list")  # "list" is only valid for transaction


def test_unknown_agent_raises():
    with pytest.raises(ValueError):
        _operation("bogus.create")
