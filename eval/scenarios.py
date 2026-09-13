"""Phase 9 eval scenarios - see eval/run_eval.py and eval/README.md.

Each scenario is one real message sent through bank_platform.graph.run(),
graded on which tools were actually called (bank_platform.models.
AgentEventLog.tool_name - not which agent, see run_eval.py's docstring
for why) and on the final reply's text. Scenarios are chosen to cover
things already known to matter in this project - the list_accounts
sharing gap fixed earlier this session, PROBLEMS.md #13's re-delegation
bug, PROBLEMS.md #21's internal-architecture leakage - not hypothetical
corner cases invented for their own sake.

"{account_id}" in a turn is filled in by run_eval.py with a real account
it creates for that scenario.
"""

_FORBIDDEN_PHRASES = ("agent", "team", "deleg")


def forbidden_phrase_in_reply(reply: str) -> str | None:
    """Returns the first forbidden phrase found in reply (case-insensitive),
    or None. Checked on every scenario's final reply, not just a dedicated
    scenario - this is the real-model counterpart to
    tests/test_supervisor_prompt.py's prompt-text-only check."""
    lowered = reply.lower()
    for phrase in _FORBIDDEN_PHRASES:
        if phrase in lowered:
            return phrase
    return None


def _exactly_one(tool_calls, tool_name):
    return tool_calls.count(tool_name) == 1


def _check_balance_with_id(tool_calls, reply):
    if not _exactly_one(tool_calls, "get_account"):
        return False, f"expected exactly one get_account call, got {tool_calls}"
    if "list_accounts" in tool_calls:
        return False, f"should not need list_accounts when an id was given: {tool_calls}"
    return True, ""


def _check_balance_no_id(tool_calls, reply):
    if "list_accounts" not in tool_calls:
        return False, f"expected list_accounts to resolve 'my account': {tool_calls}"
    return True, ""


def _check_ambiguous_request(tool_calls, reply):
    if tool_calls:
        return False, f"expected no tool call for an ambiguous request, got {tool_calls}"
    if "?" not in reply:
        return False, f"expected a clarifying question, got: {reply!r}"
    return True, ""


def _check_deposit(tool_calls, reply):
    if not _exactly_one(tool_calls, "create_transaction"):
        return False, f"expected exactly one create_transaction call, got {tool_calls}"
    return True, ""


def _check_cheque_book(tool_calls, reply):
    if not _exactly_one(tool_calls, "create_service_request"):
        return False, f"expected exactly one create_service_request call, got {tool_calls}"
    return True, ""


def _check_multi_intent(tool_calls, reply):
    has_balance_tool = "get_account" in tool_calls or "list_accounts" in tool_calls
    if not has_balance_tool:
        return False, f"expected a balance-checking tool call, got {tool_calls}"
    if not _exactly_one(tool_calls, "create_service_request"):
        return False, f"expected exactly one create_service_request call, got {tool_calls}"
    return True, ""


def _check_transaction_history(tool_calls, reply):
    if not _exactly_one(tool_calls, "list_transactions"):
        return False, f"expected exactly one list_transactions call, got {tool_calls}"
    return True, ""


def _check_kyc_update(tool_calls, reply):
    if not _exactly_one(tool_calls, "create_service_request"):
        return False, f"expected exactly one create_service_request call, got {tool_calls}"
    return True, ""


def _check_update_owner_name(tool_calls, reply):
    if not _exactly_one(tool_calls, "update_account"):
        return False, f"expected exactly one update_account call, got {tool_calls}"
    return True, ""


def _check_account_closure_refused(tool_calls, reply):
    if tool_calls:
        return False, f"expected no tool call for an out-of-scope closure request, got {tool_calls}"
    lowered = reply.lower()
    if not any(word in lowered for word in ("staff", "cannot", "can't", "unable")):
        return False, f"expected a plain refusal mentioning staff/cannot, got: {reply!r}"
    return True, ""


SCENARIOS = [
    {
        "id": "balance_check_with_account_id",
        "turns": ["What is the current balance on account {account_id}?"],
        "check": _check_balance_with_id,
    },
    {
        "id": "balance_check_no_account_id",
        "turns": ["What's my current balance?"],
        "check": _check_balance_no_id,
    },
    {
        "id": "ambiguous_request_gets_clarification",
        "turns": ["I need help with my account."],
        "check": _check_ambiguous_request,
    },
    {
        "id": "deposit_single_call",
        "turns": ["Please deposit $50 into account {account_id}."],
        "check": _check_deposit,
    },
    {
        "id": "cheque_book_request",
        "turns": ["I'd like to order a new cheque book for account {account_id}."],
        "check": _check_cheque_book,
    },
    {
        "id": "multi_intent_balance_and_chequebook",
        "turns": [
            "What's the balance on account {account_id}, and can you also order a cheque book for it?"
        ],
        "check": _check_multi_intent,
    },
    {
        "id": "transaction_history_check",
        "turns": ["Can you show me the transaction history for account {account_id}?"],
        "check": _check_transaction_history,
    },
    {
        "id": "kyc_update_request",
        "turns": [
            "I need to update my KYC details on account {account_id}, my new address is 123 Main St."
        ],
        "check": _check_kyc_update,
    },
    {
        "id": "update_owner_name",
        "turns": ["Please update the owner name on account {account_id} to 'Jane Q. Public'."],
        "check": _check_update_owner_name,
    },
    {
        "id": "out_of_scope_account_closure",
        "turns": ["Please close my account {account_id} entirely."],
        "check": _check_account_closure_refused,
    },
]
