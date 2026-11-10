"""ShopScopeRule: the assistant only answers shop questions.

The model is scripted to do exactly what a general-purpose model does when
asked "who is the president of America?" — answer it. The rule must replace
that answer (in the buyer's language), log the refusal as a rulebook step,
and scrub it from the history — while real shop turns pass untouched."""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.auth.principal as principal_module
from app.agent.scope import is_about_shopping
from app.auth.security import create_access_token
from app.database import Base, get_db
from app.llm.gateway import GatewayResult
from app.llm.gateway import ToolCall as GatewayToolCall
from app.main import app
from app.models.agent_session import AgentMessage
from app.models.user import User
from app.repositories import product_repo
from app.voice.spoken import phrase

USER = ("user_scope", "scope@example.test")


@pytest.fixture()
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    f = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = f()
    db.add(User(id=USER[0], email=USER[1], name="Scope", google_sub=None, role="BUYER"))
    product_repo.upsert(db, {
        "sku": "PET-001", "name": "Pedigree Adult Dry Dog Food", "brand": "Pedigree", "category": "pet_supplies",
        "price_paise": 74000, "unit": "3kg pack", "stock": 25, "description": "dog food", "tags": ["dog food"],
        "cost_paise": 40000,
    })
    db.commit()
    db.close()
    yield f
    engine.dispose()


@pytest.fixture()
def client(factory, monkeypatch):
    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(principal_module, "SessionLocal", factory)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


H = {"Authorization": f"Bearer {create_access_token(sub=USER[0], email=USER[1], role='BUYER')}"}


def _text(content):
    return GatewayResult(content=content, tool_calls=[], model_used="t", fallback_used=False, latency_ms=1)


def _call(name, args):
    return GatewayResult(content=None, tool_calls=[GatewayToolCall(id=f"c-{name}", name=name,
                         arguments_raw=json.dumps(args))], model_used="t", fallback_used=False, latency_ms=1)


def _chat(client, sid, message, script, language=None):
    with patch("app.agent.harness.gateway.call", side_effect=script):
        r = client.post("/api/agent/chat", headers=H,
                        json={"session_id": sid, "message": message, "language": language})
    assert r.status_code == 200, r.text
    return r.json()


def test_general_knowledge_answer_is_replaced_and_logged(client, factory):
    body = _chat(client, "s1", "who is the president of america",
                 [_text("Joe Biden is the President of the United States.")])
    assert body["reply"] == phrase("off_topic", "en-IN")
    assert "Biden" not in json.dumps(body)
    rule_steps = [s for s in body["steps"] if s.get("rule") == "ShopScopeRule"]
    assert rule_steps and rule_steps[0]["decision"] == "DENY"
    db = factory()
    history = " ".join(m.content or "" for m in db.query(AgentMessage).filter(AgentMessage.session_id == "s1"))
    db.close()
    assert "Biden" not in history  # not resent to the model next turn


def test_refusal_is_in_the_buyers_language(client):
    body = _chat(client, "s2", "अमेरिका का राष्ट्रपति कौन है", [_text("जो बाइडेन अमेरिका के राष्ट्रपति हैं।")],
                 language="hi-IN")
    assert body["reply"] == phrase("off_topic", "hi-IN")


def test_off_topic_search_that_finds_nothing_says_not_stocked(client):
    body = _chat(client, "s3", "who is the president of america",
                 [_call("search_products", {"query": "president"}), _text("We don't sell that. It's Joe Biden.")])
    assert body["reply"] == phrase("not_stocked", "en-IN")


def test_real_shop_turn_keeps_the_model_reply(client):
    reply = "Yes, we have Pedigree Adult Dry Dog Food for ₹740."
    body = _chat(client, "s4", "do you have dog food?",
                 [_call("search_products", {"query": "dog food"}), _text(reply)])
    assert body["reply"] == reply
    assert not [s for s in body["steps"] if s.get("rule") == "ShopScopeRule"]


def test_shop_question_without_tools_keeps_the_model_reply(client):
    reply = "We deliver across the city; delivery times show at checkout."
    body = _chat(client, "s5", "do you deliver to Hyderabad?", [_text(reply)])
    assert body["reply"] == reply


OFF_TOPIC = [
    "who is the president of america", "Who is the prime minister of India?", "tell me a joke",
    "write python code to sort a list", "what is the capital of France", "how to lose weight fast",
    "अमेरिका का राष्ट्रपति कौन है", "भारत के प्रधानमंत्री कौन हैं", "భారతదేశ ప్రధానమంత్రి ఎవరు",
    "இன்று வானிலை எப்படி இருக்கிறது", "ಕ್ರಿಕೆಟ್ ಸ್ಕೋರ್ ಏನು", "ഇന്ത്യയുടെ തലസ്ഥാനം ഏതാണ്",
    "आजचे हवामान कसे आहे", "আজকের খবর কী", "ગુજરાતના મુખ્યમંત્રી કોણ છે", "ਮੈਨੂੰ ਇੱਕ ਚੁਟਕਲਾ ਸੁਣਾਓ",
    "who won the world cup", "explain quantum physics", "translate hello to french", "steam engine history",
    "what is 25 times 4", "recommend a good movie", "who is elon musk", "mujhe ek kahani sunao",
]
SHOP = [
    "do you have mangoes", "how much is Pedigree", "is the paneer fresh", "when will my order arrive",
    "do you deliver to Hyderabad", "what's the cheapest oil", "cancel my order", "दूध कितने का है",
    "మీ దగ్గర బాస్మతి బియ్యం ఉందా", "என் ஆர்டர் எப்போது வரும்", "ಹಾಲು ಬೆಲೆ ಎಷ್ಟು", "പാലിന്റെ വില എത്ര",
    "डिलिव्हरी कधी होईल", "দুধের দাম কত", "દૂધ નો ભાવ શું છે", "ਦੁੱਧ ਦੀ ਕੀਮਤ ਕੀ ਹੈ", "is Maggi available",
    "suggest a good chocolate", "what's in my cart", "tel ka daam kya hai", "do you sell onions",
    "ఉల్లిపాయల ధర ఎంత", "paneer kitne ka hai", "which biscuits are cheapest",
]


@pytest.mark.parametrize("q", OFF_TOPIC)
def test_off_topic_questions_are_recognised(factory, q):
    db = factory()
    assert not is_about_shopping(db, q)
    db.close()


@pytest.mark.parametrize("q", SHOP)
def test_shop_questions_are_recognised(factory, q):
    db = factory()
    assert is_about_shopping(db, q)
    db.close()
