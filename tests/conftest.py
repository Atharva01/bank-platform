import pytest

from bank_platform.database import engine
from bank_platform.models import Base


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    Base.metadata.create_all(engine)
