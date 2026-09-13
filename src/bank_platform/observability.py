"""Phase 8 (Observability & Cost Tracker). A LangChain BaseCallbackHandler
that records one AgentEventLog row per LLM call and per tool call -
timing, token usage, an estimated cost, and success/failure. Deliberately
does NOT log prompt/reply/tool-arg content - see models.py's
AgentEventLog docstring for why.

Attached once, in graph.py's config, as `"callbacks": [event_logger]` -
this is the standard LangChain/LangGraph extension point (the same one
LangSmith tracing itself uses), so no code in llm.py, the *_tools.py
files, or the agents themselves needs to change.

A logging failure must never break a real chat request: every write is
wrapped in try/except that only logs to stderr.

Verified empirically (not assumed) that LangChain does NOT pass
`metadata` to the `*_end`/`*_error` callbacks, only to `*_start` - so
thread_id/customer_id/tool_name/model are captured once at start time and
carried forward keyed by `run_id`, rather than re-read at the end.
"""

import logging
import time
from datetime import datetime, timezone
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from bank_platform.database import SessionLocal
from bank_platform.models import AgentEventLog

logger = logging.getLogger(__name__)

# $ per 1 million tokens, (input, output). Muse Spark's actual per-token
# rate is unknown - the contributor tier reads as a flat monthly budget,
# not confirmed metered pricing - so it's deliberately absent rather than
# guessed; token counts are still recorded precisely regardless. Groq's
# rate is its last known real price (see llm.py's docstring), kept here
# for if/when it's active again.
_PRICING_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
    "openai/gpt-oss-20b": (0.075, 0.30),
}


def _estimate_cost(model: str | None, input_tokens: int | None, output_tokens: int | None) -> float | None:
    if not model or model not in _PRICING_PER_MILLION_TOKENS or input_tokens is None or output_tokens is None:
        return None
    input_rate, output_rate = _PRICING_PER_MILLION_TOKENS[model]
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000


def _record(**fields) -> None:
    db = SessionLocal()
    try:
        db.add(AgentEventLog(created_at=datetime.now(timezone.utc), **fields))
        db.commit()
    except Exception:
        logger.exception("failed to record AgentEventLog row")
    finally:
        db.close()


class ObservabilityCallbackHandler(BaseCallbackHandler):
    def __init__(self) -> None:
        # Keyed by run_id, captured at *_start, consumed at *_end/*_error -
        # metadata/model/tool name aren't reliably available past start.
        self._pending: dict[UUID, dict] = {}

    def _start(self, run_id: UUID, metadata: dict | None, **extra) -> None:
        metadata = metadata or {}
        self._pending[run_id] = {
            "start": time.monotonic(),
            "session_id": metadata.get("thread_id"),
            "customer_id": metadata.get("customer_id"),
            **extra,
        }

    def _finish(self, run_id: UUID) -> dict:
        context = self._pending.pop(run_id, None) or {"start": time.monotonic()}
        context["duration_ms"] = int((time.monotonic() - context["start"]) * 1000)
        return context

    # --- LLM calls ---

    def on_llm_start(self, serialized, prompts, *, run_id, metadata=None, **kwargs) -> None:
        self._start(run_id, metadata, model=(serialized or {}).get("kwargs", {}).get("model"))

    def on_chat_model_start(self, serialized, messages, *, run_id, metadata=None, **kwargs) -> None:
        self._start(run_id, metadata, model=(serialized or {}).get("kwargs", {}).get("model"))

    def on_llm_end(self, response: LLMResult, *, run_id, **kwargs) -> None:
        context = self._finish(run_id)

        usage = None
        try:
            message = response.generations[0][0].message
            usage = getattr(message, "usage_metadata", None)
        except (IndexError, AttributeError):
            pass
        if usage is None and response.llm_output:
            usage = response.llm_output.get("token_usage")

        prompt_tokens = usage.get("input_tokens", usage.get("prompt_tokens")) if usage else None
        completion_tokens = usage.get("output_tokens", usage.get("completion_tokens")) if usage else None
        total_tokens = usage.get("total_tokens") if usage else None

        _record(
            session_id=context.get("session_id"),
            customer_id=context.get("customer_id"),
            event_type="llm_call",
            duration_ms=context["duration_ms"],
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=_estimate_cost(context.get("model"), prompt_tokens, completion_tokens),
            success=True,
        )

    def on_llm_error(self, error: BaseException, *, run_id, **kwargs) -> None:
        context = self._finish(run_id)
        _record(
            session_id=context.get("session_id"),
            customer_id=context.get("customer_id"),
            event_type="llm_call",
            duration_ms=context["duration_ms"],
            success=False,
            error_message=str(error)[:500],
        )

    # --- Tool calls ---

    def on_tool_start(self, serialized, input_str, *, run_id, metadata=None, **kwargs) -> None:
        self._start(run_id, metadata, tool_name=(serialized or {}).get("name"))

    def on_tool_end(self, output, *, run_id, **kwargs) -> None:
        context = self._finish(run_id)
        _record(
            session_id=context.get("session_id"),
            customer_id=context.get("customer_id"),
            event_type="tool_call",
            tool_name=context.get("tool_name"),
            duration_ms=context["duration_ms"],
            success=True,
        )

    def on_tool_error(self, error: BaseException, *, run_id, **kwargs) -> None:
        context = self._finish(run_id)
        _record(
            session_id=context.get("session_id"),
            customer_id=context.get("customer_id"),
            event_type="tool_call",
            tool_name=context.get("tool_name"),
            duration_ms=context["duration_ms"],
            success=False,
            error_message=str(error)[:500],
        )


event_logger = ObservabilityCallbackHandler()
