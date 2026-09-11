"""Shared LLM client. OpenAI-compatible API shape (base_url + api_key) so
swapping providers is a config change, not a code change — agents never
depend on a provider-specific SDK.

Currently: Groq (openai/gpt-oss-20b), via GROQ_API_KEY in .env.

Model choice note: DeepSeek's deepseek-flash and Qwen3 (both self-hosted via
Ollama and Groq-hosted qwen/qwen3.6-27b) were tried first and rejected —
both are "thinking" models that either require reasoning_content to be
echoed back on every multi-turn call (DeepSeek, breaks LangGraph's
supervisor handoff which is inherently multi-turn) or leak raw <think>...
</think> blocks straight into the content field regardless of /no_think
(Qwen3). gpt-oss-20b returns clean content with no reasoning pass-back
requirement, and is cheap ($0.075/$0.30 per 1M input/output tokens).

Re-checked a third time (PROBLEMS.md #16) with `deepseek-v4-flash` +
`extra_body={"thinking": {"type": "disabled"}}`, which does stop the
reasoning_content crash — but on a real multi-turn supervisor run it
silently hallucinated a completed account-opening (confident natural-
language "done" replies) without ever calling a tool: nothing was written
to the database. That's a worse failure mode than the crash it replaced
(silent, not loud), so DeepSeek is rejected again. Reverted to Groq.
"""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

llm = ChatOpenAI(
    model="openai/gpt-oss-20b",
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ["GROQ_API_KEY"],
    temperature=0,
    max_tokens=500,  # keeps requests within Groq's free-tier output-tokens-per-minute limit
)
# Note: gpt-oss-20b occasionally emits a tool-call payload Groq's own parser
# can't parse (openai.BadRequestError: output_parse_failed) - observed as
# transient, not systematic. Retrying belongs at the graph-invocation level
# (graph.py's invoke_supervisor), not here - .with_retry() on this client
# would break .bind_tools(), which create_agent() needs internally.
