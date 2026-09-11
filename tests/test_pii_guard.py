"""Zero-LLM-call tests for pii_guard.py's reversible tokenization (Phase 5
- PII Redaction). These verify the mechanism itself - tokenize/detokenize
round-tripping, the pii_guard decorator's arg/result handling, and its
composition with tool_utils' existing decorators - not whether a live
model actually uses tokens correctly, which needs a real multi-turn
supervisor run (see PROGRESS.md Phase 5's verification notes).
"""

from langchain_core.tools import ToolException

from bank_platform import pii_guard


def teardown_function(_):
    pii_guard._token_maps.clear()


def test_tokenize_is_stable_for_the_same_value():
    token1 = pii_guard.tokenize_dict({"id": "abc-123"}, {"id": "ACCOUNT_ID"}, "t1")["id"]
    token2 = pii_guard.tokenize_dict({"id": "abc-123"}, {"id": "ACCOUNT_ID"}, "t1")["id"]
    assert token1 == token2
    assert token1 == "[ACCOUNT_ID_1]"


def test_tokenize_assigns_new_token_for_a_new_value():
    pii_guard.tokenize_dict({"id": "abc-123"}, {"id": "ACCOUNT_ID"}, "t1")
    second = pii_guard.tokenize_dict({"id": "xyz-789"}, {"id": "ACCOUNT_ID"}, "t1")["id"]
    assert second == "[ACCOUNT_ID_2]"


def test_tokens_are_isolated_per_thread():
    pii_guard.tokenize_dict({"id": "abc-123"}, {"id": "ACCOUNT_ID"}, "t1")
    other_thread_token = pii_guard.tokenize_dict({"id": "abc-123"}, {"id": "ACCOUNT_ID"}, "t2")["id"]
    assert other_thread_token == "[ACCOUNT_ID_1]"  # fresh counter, not "_2"


def test_tokenize_dict_leaves_unlisted_fields_untouched():
    result = pii_guard.tokenize_dict(
        {"id": "abc-123", "status": "pending"}, {"id": "ACCOUNT_ID"}, "t1"
    )
    assert result["status"] == "pending"


def test_tokenize_dict_handles_a_list_of_dicts():
    result = pii_guard.tokenize_dict(
        [{"id": "a"}, {"id": "b"}], {"id": "TRANSACTION_ID"}, "t1"
    )
    assert result[0]["id"] == "[TRANSACTION_ID_1]"
    assert result[1]["id"] == "[TRANSACTION_ID_2]"


def test_tokenize_skips_none_values():
    result = pii_guard.tokenize_dict({"description": None}, {"description": "DESCRIPTION"}, "t1")
    assert result["description"] is None


def test_detokenize_args_restores_real_values():
    pii_guard.tokenize_dict({"id": "real-uuid"}, {"id": "ACCOUNT_ID"}, "t1")
    real_kwargs = pii_guard.detokenize_args({"id": "[ACCOUNT_ID_1]"}, "t1")
    assert real_kwargs["id"] == "real-uuid"


def test_detokenize_args_leaves_non_token_strings_and_non_strings_alone():
    real_kwargs = pii_guard.detokenize_args({"balance": 50.0, "note": "hello"}, "t1")
    assert real_kwargs == {"balance": 50.0, "note": "hello"}


def test_detokenize_restores_real_values_in_free_text():
    pii_guard.tokenize_dict({"id": "real-uuid", "balance": 500.0}, {"id": "ACCOUNT_ID", "balance": "BALANCE"}, "t1")
    text = "Account [ACCOUNT_ID_1] has balance [BALANCE_1]."
    assert pii_guard.detokenize(text, "t1") == "Account real-uuid has balance 500.0."


def test_detokenize_is_a_no_op_for_an_unknown_thread():
    assert pii_guard.detokenize("nothing to see here", "never-seen-thread") == "nothing to see here"


def test_sanitize_incoming_replaces_a_known_real_value():
    pii_guard.tokenize_dict({"id": "b5cedb0e-real"}, {"id": "ACCOUNT_ID"}, "t1")
    text = pii_guard.sanitize_incoming("here is my account b5cedb0e-real", "t1")
    assert text == "here is my account [ACCOUNT_ID_1]"


def test_sanitize_incoming_is_a_no_op_before_anything_is_known():
    assert pii_guard.sanitize_incoming("my account is b5cedb0e-real", "t1") == "my account is b5cedb0e-real"


def test_forget_thread_clears_its_map():
    pii_guard.tokenize_dict({"id": "abc"}, {"id": "ACCOUNT_ID"}, "t1")
    pii_guard.forget_thread("t1")
    assert pii_guard.detokenize("[ACCOUNT_ID_1]", "t1") == "[ACCOUNT_ID_1]"  # nothing left to restore


class _FakeConfig(dict):
    pass


def test_pii_guard_detokenizes_args_before_calling_and_tokenizes_the_result():
    calls = []

    def fake_tool(id):
        calls.append(id)
        return {"id": id, "owner_name": "Alice", "status": "active"}

    fake_tool.__annotations__ = {"id": str, "return": dict}  # no "config" - mirrors tool_safe-only tools

    wrapped = pii_guard.pii_guard(fake_tool, {"id": "ACCOUNT_ID", "owner_name": "OWNER_NAME"})

    # Seed the thread with a known account id, as a real tool result would.
    pii_guard.tokenize_dict({"id": "real-account-id"}, {"id": "ACCOUNT_ID"}, "t1")
    config = {"configurable": {"thread_id": "t1"}}

    result = wrapped(id="[ACCOUNT_ID_1]", config=config)

    assert calls == ["real-account-id"]  # the real function saw the real id, not the token
    assert result["id"] == "[ACCOUNT_ID_1]"
    assert result["owner_name"] == "[OWNER_NAME_1]"
    assert result["status"] == "active"  # not in field_categories, left alone


def test_pii_guard_forwards_config_only_when_the_inner_function_declares_it():
    received = {}

    def config_requiring_inner(*, config, **kwargs):
        received["config"] = config
        received["kwargs"] = kwargs
        return {"id": kwargs.get("id")}

    config_requiring_inner.__annotations__ = {"config": "RunnableConfig"}

    wrapped = pii_guard.pii_guard(config_requiring_inner, {"id": "ACCOUNT_ID"})
    config = {"configurable": {"thread_id": "t2"}}
    wrapped(id="abc", config=config)

    assert received["config"] == config

    def plain_inner(**kwargs):
        # Would crash on an unexpected "config" kwarg landing in **kwargs
        # and being forwarded to a real server function - this is exactly
        # the bug pii_guard's forwards_config check exists to avoid.
        assert "config" not in kwargs
        return {"id": kwargs.get("id")}

    plain_inner.__annotations__ = {"id": str, "return": dict}
    wrapped_plain = pii_guard.pii_guard(plain_inner, {"id": "ACCOUNT_ID"})
    wrapped_plain(id="abc", config={"configurable": {"thread_id": "t3"}})


def test_pii_guard_lets_tool_exceptions_propagate():
    def failing_tool(**kwargs):
        raise ToolException("boom")

    failing_tool.__annotations__ = {"return": dict}
    wrapped = pii_guard.pii_guard(failing_tool, {})
    try:
        wrapped(config={"configurable": {"thread_id": "t1"}})
        assert False, "expected ToolException"
    except ToolException as e:
        assert str(e) == "boom"
