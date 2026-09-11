import pytest

from database import engine
from models import Base


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    Base.metadata.create_all(engine)
