"""Phase 9 - Agent Evaluation Suite. Run on-demand only:

    uv run python eval/run_eval.py

NOT part of `pytest`/CI - deliberately kept outside tests/ so a plain
`uv run pytest` (today's whole suite, and any future CI) never collects
or runs this by accident. Every run makes real, paid LLM calls against
whichever provider llm.py currently points at (Muse Spark) - see
eval/README.md for the per-run cost estimate before running this.

Grades on which TOOLS were actually called
(bank_platform.models.AgentEventLog.tool_name), not which agent -
agent_name is a known-unreliable field (PROBLEMS.md #23), so no scenario
here ever depends on it. tests/test_supervisor_prompt.py already
regression-tests the prompt TEXT for free; this is the real-model
counterpart that costs live calls, which is exactly why it isn't run on
every commit.
"""

import sys
import uuid

from bank_platform import accounts_server
from bank_platform.database import SessionLocal
from bank_platform.graph import run
from bank_platform.models import AgentEventLog

from scenarios import SCENARIOS, forbidden_phrase_in_reply


def _tool_calls_for_session(session_id: str) -> list[str]:
    db = SessionLocal()
    try:
        rows = (
            db.query(AgentEventLog)
            .filter(AgentEventLog.session_id == session_id, AgentEventLog.event_type == "tool_call")
            .order_by(AgentEventLog.created_at)
            .all()
        )
        return [row.tool_name for row in rows if row.tool_name]
    finally:
        db.close()


def _cleanup(account_id: str, session_id: str) -> None:
    # accounts_server.delete_account cascades to related transactions/
    # service requests (PROBLEMS.md #16) - reuses that instead of raw
    # per-table deletes.
    accounts_server.delete_account(account_id)
    db = SessionLocal()
    try:
        db.query(AgentEventLog).filter(AgentEventLog.session_id == session_id).delete()
        db.commit()
    finally:
        db.close()


def run_scenario(scenario: dict) -> tuple[bool, str]:
    customer_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    account = accounts_server.create_account(owner_name="Eval Customer", balance=500, customer_id=customer_id)
    account_id = account["id"]

    try:
        reply = ""
        for turn in scenario["turns"]:
            reply = run(turn.format(account_id=account_id), session_id, customer_id)

        leaked = forbidden_phrase_in_reply(reply)
        if leaked:
            return False, f"reply leaked internal framing ({leaked!r}): {reply!r}"

        tool_calls = _tool_calls_for_session(session_id)
        return scenario["check"](tool_calls, reply)
    finally:
        _cleanup(account_id, session_id)


def main() -> int:
    total = len(SCENARIOS)
    print(f"Running {total} eval scenarios against the live model (~{total}+ real LLM calls)...\n")

    failures = 0
    for scenario in SCENARIOS:
        passed, detail = run_scenario(scenario)
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {scenario['id']}" + (f" - {detail}" if detail else ""))
        if not passed:
            failures += 1

    print(f"\n{total - failures}/{total} passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
