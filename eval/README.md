# Agent Evaluation Suite (Phase 9)

Grades the live model's actual routing/tool-call behavior against
`bank_platform.graph.run()`, using real, paid LLM calls. This is **not**
part of `pytest` or CI - it lives outside `tests/` on purpose so a plain
`uv run pytest` never triggers it by accident.

## Running it

```bash
uv run python eval/run_eval.py
```

**Cost: ~10 live LLM calls per full run** (one per scenario in
`scenarios.py`), against whichever provider `llm.py` currently points at
(Muse Spark, a paid/budget-constrained provider - see PROBLEMS.md
#18-#20). Run this deliberately, not habitually.

## What it checks

Each scenario sends one real message through the actual supervisor graph,
then grades:
- **Which tools were actually called** (from
  `bank_platform.models.AgentEventLog`, Phase 8's instrumentation) - e.g.
  did "what's my balance" with no account id trigger `list_accounts`,
  did a clear single-intent request call exactly one tool and not
  duplicate it.
- **The final reply's text** - every scenario checks for leaked internal
  framing ("agent", "team", "deleg" - the same rule
  `tests/test_supervisor_prompt.py` checks at the prompt-text level, this
  time against real model output).

It deliberately does **not** grade on `agent_name` - that field is
known-unreliable (a real call recorded `agent_name: None` on every row,
see PROBLEMS.md #23), so no scenario here depends on it.

## When a scenario fails

Read the actual `AgentEventLog` rows and the real reply for that
session before changing anything - decide whether it's a real prompt
regression (fix in `graph.py`) or the scenario itself needs adjusting
(fix in `scenarios.py`). Don't loosen a check just to make it pass.
