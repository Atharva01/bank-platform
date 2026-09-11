from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+psycopg://bank:bank@localhost:5432/bank_platform"

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine)
