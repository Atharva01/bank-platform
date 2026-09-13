import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

# Was a hardcoded literal until Phase 7 (Edge Layer) - .env's own
# DATABASE_URL line existed but was never actually read, which only
# "worked" because local dev always runs on the same host as Postgres.
# Inside Docker Compose the backend container must reach Postgres by
# service name (e.g. "db"), not "localhost" - the default below keeps
# today's local-dev value unchanged, Compose sets the real one.
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://bank:bank@localhost:5432/bank_platform"
)

# connect_timeout: without it, a dead/unreachable Postgres (e.g. Docker
# Desktop's engine crashing, hit for real this session) can hang a request
# indefinitely instead of failing fast - same principle as llm.py's
# `timeout` on the LLM client.
engine = create_engine(DATABASE_URL, connect_args={"connect_timeout": 10})

SessionLocal = sessionmaker(bind=engine)
