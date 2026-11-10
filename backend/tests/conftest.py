import pytest

from app.agent import titles
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(autouse=True)
def _no_background_titles(monkeypatch):
    """Conversation titles are generated on a background thread in production
    (app/agent/titles.py). Most tests here script the model with an iterator —
    `patch("app.agent.harness.gateway.call", side_effect=...)` — and assert on
    that exact sequence of responses. A title call arriving on the same
    gateway singleton from another thread would consume one of them at a
    nondeterministic point, so titling is disabled for the suite.

    Tests that exercise titling call generate_title() directly instead; see
    tests/test_conversation_history.py.
    """
    monkeypatch.setattr(titles, "BACKGROUND_TITLES_ENABLED", False)


@pytest.fixture(autouse=True)
def _no_live_llm_in_tests(monkeypatch):
    """Tests script the model by patching `gateway.call`. Background jobs use
    `call_low_priority`, which would otherwise go straight to the real
    last-resort provider — route it through the patched `call` instead, and
    run demand capture inline so tests can assert on it."""
    from app.demand import capture
    from app.llm.gateway import gateway

    monkeypatch.setattr(capture, "BACKGROUND_CAPTURE_ENABLED", False)
    monkeypatch.setattr(gateway, "call_low_priority", lambda messages, tools: gateway.call(messages, tools))
