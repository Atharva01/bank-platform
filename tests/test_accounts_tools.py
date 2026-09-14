from bank_platform.accounts_tools import ACCOUNTS_TOOLS


def test_update_account_tool_schema_has_no_balance_field():
    # Phase 10 security review: update_account's chat tool used to have no
    # explicit args_schema, so LangChain inferred one straight from
    # accounts_server.update_account's signature - including `balance`,
    # letting a customer just ask the assistant to set their own balance.
    # A customer's balance may only ever change via a deposit/withdrawal
    # (transaction_agent), never by editing the field directly.
    update_account_tool = next(t for t in ACCOUNTS_TOOLS if t.name == "update_account")
    assert "balance" not in update_account_tool.args_schema.model_fields
