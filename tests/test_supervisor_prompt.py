"""Structural regression guard on the supervisor/agent prompt CONTENT -
zero LLM calls, so it's cheap to run constantly in CI. This can only catch
"someone silently dropped a rule while editing the prompt string"; it
cannot verify the LLM actually follows these instructions on ambiguous or
multi-intent input. That needs a real evaluation harness run against the
live model - tracked as Phase 9 (Agent Evaluation Suite) in PROGRESS.md,
deliberately not attempted here to avoid live-LLM calls in a unit test.
"""

from bank_platform.graph import (
    ACCOUNTS_AGENT_PROMPT,
    SERVICE_AGENT_PROMPT,
    SUPERVISOR_PROMPT,
    TRANSACTION_AGENT_PROMPT,
)


def test_supervisor_names_every_sub_agent():
    for name in ("accounts_agent", "transaction_agent", "service_agent"):
        assert name in SUPERVISOR_PROMPT


def test_supervisor_states_each_agents_limits():
    # each agent's own job description should be paired with an explicit
    # "does NOT" boundary, not just a list of what it does - this is the
    # part that regressed once already (see PROGRESS.md change log)
    for marker in ("Does NOT close accounts", "Does NOT open accounts", "Does NOT move money"):
        assert marker in SUPERVISOR_PROMPT


def test_supervisor_forbids_redelegation():
    assert "do NOT delegate again" in SUPERVISOR_PROMPT
    assert "exactly once" in SUPERVISOR_PROMPT


def test_supervisor_has_a_fallback_for_unclear_requests():
    assert "do not guess" in SUPERVISOR_PROMPT
    assert "clarify" in SUPERVISOR_PROMPT


def test_accounts_agent_prompt_disclaims_account_closure():
    # accounts_tools.py deliberately doesn't expose delete_account - the
    # agent must be told this explicitly, or it will try a workaround
    # instead of telling the user closure isn't available here
    assert "cannot close an account" in ACCOUNTS_AGENT_PROMPT


def test_transaction_agent_prompt_forbids_duplicate_tool_calls():
    assert "never call" in TRANSACTION_AGENT_PROMPT.lower()


def test_service_agent_prompt_is_non_empty():
    assert len(SERVICE_AGENT_PROMPT) > 0
