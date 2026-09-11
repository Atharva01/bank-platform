from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+psycopg://bank:bank@localhost:5432/bank_platform"

# connect_timeout: without it, a dead/unreachable Postgres (e.g. Docker
# Desktop's engine crashing, hit for real this session) can hang a request
# indefinitely instead of failing fast - same principle as llm.py's
# `timeout` on the LLM client.
engine = create_engine(DATABASE_URL, connect_args={"connect_timeout": 10})

SessionLocal = sessionmaker(bind=engine)
