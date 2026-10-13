import json
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.core.database import Base, get_db
from app.core.config import get_settings
from app.main import app
from app.models.user import Role
from app.schemas.user import UserCreate
from app.services import user_service
from tests.fakes import RecordingFake, ScriptedChat

get_settings().bcrypt_rounds = 4  # fast password hashing for tests only


@pytest.fixture()
def db_session():
    """A fresh empty database for every test: in-memory SQLite, or PostgreSQL if TEST_DATABASE_URL is set."""
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        engine = create_engine(url)
        Base.metadata.drop_all(engine)
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session() as session:
        yield session
    if url:
        session.close()
        Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    # No "with" block on purpose: that would run the startup code against the real database.
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def make_user(db_session):
    def _make(email="admin@example.com", role=Role.ADMIN, password="password123", name="Test User"):
        return user_service.create_user(db_session, UserCreate(email=email, full_name=name, password=password, role=role))
    return _make


@pytest.fixture()
def login_as(client):
    """Log in as a user (switching users if someone else is logged in)."""
    def _login(email, password="password123"):
        client.cookies.clear()
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
    return _login


@pytest.fixture()
def team(make_user):
    """An admin, a manager and two sales reps."""
    return {
        "admin": make_user("admin@example.com", Role.ADMIN, name="Ada Admin"),
        "manager": make_user("manager@example.com", Role.MANAGER, name="Max Manager"),
        "rep1": make_user("rep1@example.com", Role.SALES_REP, name="Riya Rep"),
        "rep2": make_user("rep2@example.com", Role.SALES_REP, name="Sam Rep"),
    }


@pytest.fixture(autouse=True)
def no_real_ai_key(monkeypatch):
    """Tests must never talk to a real AI service, even if a developer has a key in .env."""
    monkeypatch.setattr(get_settings(), "google_api_key", "")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    monkeypatch.setattr(get_settings(), "openai_api_key", "")


@pytest.fixture()
def agent_ai(monkeypatch):
    def _install(*script, repeat_last=False, fail_with=""):
        fake = ScriptedChat(script=list(script), repeat_last=repeat_last, fail_with=fail_with)
        monkeypatch.setattr("app.agent.service.get_llm", lambda: fake)
        return fake
    return _install


@pytest.fixture()
def inner_ai(monkeypatch):
    """The AI used inside the 'score a lead' and 'write an email' tools."""
    def _install(*answers):
        fake = RecordingFake(responses=[a if isinstance(a, str) else json.dumps(a) for a in answers])
        monkeypatch.setattr("app.services.ai_service.get_llm", lambda: fake)
        return fake
    return _install


