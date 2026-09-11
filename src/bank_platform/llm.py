"""Shared LLM client. OpenAI-compatible API shape (base_url + api_key) so
swapping providers is a config change, not a code change — agents never
depend on a provider-specific SDK.

Currently: DeepSeek (deepseek-flash), via DEEPSEEK_API_KEY in .env.
"""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

llm = ChatOpenAI(
    model="deepseek-flash",
    base_url="https://api.deepseek.com",
    api_key=os.environ["DEEPSEEK_API_KEY"],
    temperature=0,
)
