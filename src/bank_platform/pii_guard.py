"""Reversible tokenization between the agent/tool layer and the LLM
(Phase 5 - PII Redaction). A real value is swapped for a stable
per-conversation token before a tool's result reaches the LLM, and
swapped back at the two points that need real data: right before a tool
actually executes (detokenize_args), and in the final reply text shown to
the user (detokenize, called from graph.py's run()).

Scope is deliberately narrow - currently just Account.owner_name (see
accounts_tools.py). IDs, balances, amounts, and free-text fields were all
tokenized at first, but that made almost every field in a tool result a
token, which measurably increased tool-call hallucination in live testing
- a context this templated seems to degrade the model's reliability more
than the redaction is worth for data that (a) is mostly not personal data
in the traditional sense (an opaque UUID, a balance) and (b) the
assistant functionally needs to reason over correctly. See PROBLEMS.md
#21. The mechanism below is generic and would support tokenizing more
fields again if a future model proves more reliable with a templated
context - the narrow scope lives in each *_tools.py file's
field_categories dict, not here.

Explicitly does NOT attempt general PII detection on free-form text a
user types before any tool has touched it - that needs NER/pattern
matching, which conflicts with this project's no-extra-LLM-calls and
determinism principles (see PROGRESS.md Phase 5). What IS covered: named
fields that flow through a tool call's arguments or a tool result -
the deterministic part the app actually controls.
"""

import re
from functools import wraps

from langchain_core.runnables import RunnableConfig

_TOKEN_PATTERN = re.compile(r"\[([A-Z_]+)_(\d+)\]")


class _ThreadTokenMap:
    """One conversation's real-value <-> token mapping. Keyed by
    (category, str(value)), not by field name - so the same real UUID
    always maps to the same token within a thread regardless of which
    field it came from (an Account's own id and a Transaction's
    account_id FK reference share one token when they're the same value).
    """

    def __init__(self) -> None:
        self._forward: dict[tuple[str, str], str] = {}
        self._reverse: dict[str, str] = {}
        self._counters: dict[str, int] = {}

    def tokenize(self, value, category: str):
        if value is None:
            return value
        key = (category, str(value))
        existing = self._forward.get(key)
        if existing is not None:
            return existing
        self._counters[category] = self._counters.get(category, 0) + 1
        token = f"[{category}_{self._counters[category]}]"
        self._forward[key] = token
        self._reverse[token] = str(value)
        return token

    def detokenize(self, text):
        if not isinstance(text, str):
            return text
        return _TOKEN_PATTERN.sub(lambda m: self._reverse.get(m.group(0), m.group(0)), text)

    def sanitize_incoming(self, text: str) -> str:
        """Replaces any ALREADY-KNOWN real value found verbatim in free
        text with its existing token - e.g. a user pasting back an
        account ID the system gave them earlier in this conversation.
        Longest real values first, so a short value that happens to be a
        substring of a longer one can't corrupt the longer replacement."""
        if not text:
            return text
        for (_category, real_value), token in sorted(
            self._forward.items(), key=lambda item: len(item[0][1]), reverse=True
        ):
            if real_value and real_value in text:
                text = text.replace(real_value, token)
        return text


# Process-local, keyed by thread_id - same lifecycle as
# tool_utils._completed_calls; cleaned up together in graph.py's session
# expiry path via forget_thread().
_token_maps: dict[str, _ThreadTokenMap] = {}


def _map_for(thread_id: str) -> _ThreadTokenMap:
    return _token_maps.setdefault(thread_id, _ThreadTokenMap())


def tokenize_dict(data, field_categories: dict[str, str], thread_id: str):
    """Tokenizes the named fields of a tool-result dict (or a list of
    dicts, e.g. list_transactions), leaving fields not listed in
    field_categories (status, request_type - operational enums, not PII)
    untouched."""
    token_map = _map_for(thread_id)

    def _tokenize_one(item: dict) -> dict:
        result = dict(item)
        for field, category in field_categories.items():
            if field in result:
                result[field] = token_map.tokenize(result[field], category)
        return result

    if isinstance(data, list):
        return [_tokenize_one(item) for item in data]
    return _tokenize_one(data)


def detokenize_args(kwargs: dict, thread_id: str) -> dict:
    """Swaps any token found in a string-valued arg back to its real value
    before a tool actually executes - the LLM only ever saw tokens, but
    the real function needs a real account ID to look up, a real amount
    to apply, and so on."""
    token_map = _map_for(thread_id)
    return {
        key: token_map.detokenize(value) if isinstance(value, str) else value
        for key, value in kwargs.items()
    }


def detokenize(text: str, thread_id: str) -> str:
    """Swaps tokens in the final reply text back to real values before
    it's shown to the user - called once, from graph.py's run()."""
    token_map = _token_maps.get(thread_id)
    if token_map is None:
        return text
    return token_map.detokenize(text)


def sanitize_incoming(text: str, thread_id: str) -> str:
    """Replaces any already-known real value found verbatim in an
    incoming user message with its existing token, before the message is
    added to the graph state - catches a user pasting back an ID/name the
    system already issued them this conversation. Does NOT attempt to
    detect new/unknown PII (see module docstring); a no-op for a thread
    with no token map yet (nothing known to substitute)."""
    token_map = _token_maps.get(thread_id)
    if token_map is None:
        return text
    return token_map.sanitize_incoming(text)


def forget_thread(thread_id: str) -> None:
    """Drops a thread's token map - called from graph.py's session-expiry
    path alongside tool_utils._completed_calls cleanup, so both share one
    lifecycle instead of drifting apart."""
    _token_maps.pop(thread_id, None)


def pii_guard(func, field_categories: dict[str, str]):
    """Outermost wrapper around a tool function: detokenizes incoming args
    to real values before the real call runs, then tokenizes the real
    result's named fields before it becomes visible to the LLM. Must be
    the outermost layer (wraps tool_safe/idempotent, not the other way
    around) so idempotent's dedup key is computed on real values, and so
    this is the function LangChain's StructuredTool.from_function actually
    builds a schema from and calls.

    Uses the same RunnableConfig-injection technique as
    tool_utils.idempotent() to get thread_id without it reaching the
    LLM-visible tool schema.
    """
    # Only forward `config` to the inner function if it actually declares
    # one (idempotent()-wrapped functions do, via the same annotation
    # trick this function uses below; tool_safe-only functions don't, and
    # would silently swallow an unexpected `config` kwarg into **kwargs,
    # crashing the real server function it eventually reaches). Checked
    # via the wrapper's own __annotations__ dict directly (not
    # inspect.signature, which would unwrap through functools.wraps'
    # __wrapped__ chain straight past idempotent's own signature).
    forwards_config = "config" in getattr(func, "__annotations__", {})

    @wraps(func)
    def wrapper(*args, config: RunnableConfig, **kwargs):
        thread_id = (config or {}).get("configurable", {}).get("thread_id", "")
        real_kwargs = detokenize_args(kwargs, thread_id)
        if forwards_config:
            result = func(*args, config=config, **real_kwargs)
        else:
            result = func(*args, **real_kwargs)
        return tokenize_dict(result, field_categories, thread_id)

    # See tool_utils.idempotent()'s identical comment: @wraps copies
    # __annotations__ by reference, so it must be copied before mutating
    # or this would silently pollute the wrapped function's own dict too.
    wrapper.__annotations__ = dict(wrapper.__annotations__)
    wrapper.__annotations__["config"] = RunnableConfig
    return wrapper
