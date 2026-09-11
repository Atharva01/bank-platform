"""Shared LLM client. OpenAI-compatible API shape (base_url + api_key) so
swapping providers is a config change, not a code change — agents never
depend on a provider-specific SDK.

Currently: Meta Muse Spark (`muse-spark-1.3-contributor`), via
MUSE_API_KEY in .env. Switched from Groq (`openai/gpt-oss-20b`) after Groq
exhausted its 3-retry budget on a live request (its own tool-call parser
occasionally can't parse gpt-oss-20b's output - "transient, not
systematic" per the retry logic in graph.py, but transient enough to hit
3 times in a row here). Muse Spark was already live-tested and validated
as a working alternative (PROBLEMS.md #18) before this switch - passed the
same real multi-turn supervisor test (genuine tool calls, correct DB
writes, no hallucination) that DeepSeek failed three times (PROBLEMS.md
#10, #14, #17). Needs `max_tokens=2048` (not 500) since it's more verbose
than gpt-oss-20b. This is a paid model (contributor tier, ~$20/mo budget)
versus Groq's free tier - an explicit cost-for-reliability tradeoff, made
after Groq's transient failure actually surfaced in the live chat UI, not
a routine swap.

Provider history, in case Muse Spark needs to be reverted:
- DeepSeek's deepseek-flash/deepseek-v4-flash and Qwen3 (self-hosted via
  Ollama and Groq-hosted qwen/qwen3.6-27b) were tried and rejected —
  either require reasoning_content echoed back on every multi-turn call
  (DeepSeek, breaks LangGraph's supervisor handoff) or leak raw
  <think>...</think> blocks into content (Qwen3), or - even with thinking
  mode explicitly disabled - silently hallucinate completed actions
  without calling a tool (DeepSeek, PROBLEMS.md #17).
- Groq's `openai/gpt-oss-20b` (free tier, $0.075/$0.30 per 1M input/output
  tokens) was the active provider before this switch: clean content, no
  reasoning pass-back requirement, but its own tool-call parser
  occasionally rejects valid-looking output (PROBLEMS.md #12), and that
  failure exhausted graph.py's retry budget at least once in real use.
"""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

llm = ChatOpenAI(
    model="muse-spark-1.3-contributor",
    base_url="https://api.meta.ai/v1",
    api_key=os.environ["MUSE_API_KEY"],
    temperature=0,
    max_tokens=2048,
)
