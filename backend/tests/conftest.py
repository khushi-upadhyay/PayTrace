import os
import sys
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.db.base import Base
from app.api.dependencies import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.core.config import settings
from app.main import app

# Ensure tests default to clean mock mode unless explicitly overridden in specific tests
settings.PAYPAL_CLIENT_ID = ""
settings.PAYPAL_CLIENT_SECRET = ""
settings.PAYPAL_WEBHOOK_ID = ""
settings.AI_API_KEY = ""
settings.APP_ENV = "test"

TEST_DB_URL = "sqlite:///:memory:"

@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def db_session(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    SessionTest = sessionmaker(bind=connection)
    session = SessionTest()

    yield session

    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    # Operator routes need a login; individual tests use the auth_client fixture to exercise it.
    app.dependency_overrides[get_current_user] = lambda: User(id="test-user", name="Test", email="t@example.com", password_hash="x", role="Payments Operator")
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
