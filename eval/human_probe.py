#!/usr/bin/env python
"""Everyday questions real shoppers ask — answered instantly and correctly?

    python eval/human_probe.py

Each line is one fresh conversation turn in a shop that already has one
paid order (2 milk + 1 bread) and a cart with 1 Maggi + 2 salt. The model is
switched OFF: a turn that needs it shows "→ MODEL". For the rest we check the
reply is the right kind of answer, in the buyer's language.
"""

import sys
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "backend"))
sys.path.insert(0, str(_ROOT / "eval"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from agent_live import USER, cart_of, make_db  # noqa: E402

from app.agent import harness  # noqa: E402
from app.orders import repository as order_repo  # noqa: E402
from app.payments import service as payment_service  # noqa: E402
from app.repositories import agent_session_repo  # noqa: E402
from app.services import cart_service  # noqa: E402
from app.schemas.cart import CartItemCreate  # noqa: E402

# (language, what the buyer says, words the reply must contain (any), expected cart change or None)
PROBES = [
    # past orders — the screenshot
    ("en-IN", "Tell me about my old order.", ["order", "Milk"], None),
    ("en-IN", "what was my last order", ["order"], None),
    ("te-IN", "నా పాత ఆర్డర్ గురించి చెప్పు", ["ఆర్డర్"], None),
    ("te-IN", "నా చివరి ఆర్డర్ ఏమిటి?", ["ఆర్డర్"], None),
    ("hi-IN", "मेरा पिछला ऑर्डर क्या था?", ["ऑर्डर"], None),
    ("ta-IN", "என் கடைசி ஆர்டர் என்ன?", ["ஆர்டர்"], None),
    ("kn-IN", "ನನ್ನ ಹಿಂದಿನ ಆರ್ಡರ್ ಏನು?", ["ಆರ್ಡರ್"], None),
    ("te-IN", "naa last order details cheppu", ["ఆర్డర్"], None),
    # wallet
    ("en-IN", "what's my wallet balance?", ["wallet"], None),
    ("te-IN", "నా వాలెట్‌లో ఎంత ఉంది?", ["వాలెట్"], None),
    ("hi-IN", "मेरे वॉलेट में कितने पैसे हैं?", ["वॉलेट"], None),
    # price
    ("en-IN", "how much is milk?", ["₹"], None),
    ("te-IN", "పాలు ఎంత?", ["₹"], None),
    ("hi-IN", "दूध कितने का है?", ["₹"], None),
    ("ta-IN", "பால் என்ன விலை?", ["₹"], None),
    ("te-IN", "బ్రెడ్ ధర ఎంత?", ["₹"], None),
    # cart
    ("te-IN", "నా కార్ట్‌లో ఏముంది?", ["కార్ట్"], None),
    ("hi-IN", "सब हटा दो", ["खाली"], {}),
    ("te-IN", "కార్ట్ ఖాళీ చేయండి", ["ఖాళీ"], {}),
    ("en-IN", "empty my cart", ["empt"], {}),
    # pay
    ("te-IN", "బిల్ కట్టాలి, చెల్లించండి", ["₹"], None),
    ("hi-IN", "पेमेंट कर दो", ["₹"], None),
    ("en-IN", "checkout please", ["₹"], None),
    # greetings / switching
    ("te-IN", "నమస్కారం", ["నమస్కారం"], None),
    ("hi-IN", "धन्यवाद", ["स्वागत"], None),
    ("te-IN", "హిందీలో మాట్లాడు", ["हिन्दी"], None),
    ("en-IN", "what do you have?", ["We have"], None),
    # simple adds
    ("te-IN", "రెండు గుడ్లు వేయండి", ["గుడ్లు", "కార్ట్"], {"GRO-008": 1, "GRO-004": 2, "KIR-011": 2}),
    ("hi-IN", "एक किलो चीनी चाहिए", ["चीनी", "कार्ट"], {"GRO-008": 1, "GRO-004": 2, "KIR-004": 1}),
    ("te-IN", "ఉప్పు తీసేయండి", ["ఉప్పు"], {"GRO-008": 1}),
]


def seed(db) -> None:
    """One paid order (2 milk + 1 bread), then a fresh cart with 1 Maggi + 2 salt."""
    cart_service.add_item(db, USER, CartItemCreate(sku="DAI-001", quantity=2))
    cart_service.add_item(db, USER, CartItemCreate(sku="KIR-012", quantity=1))
    sess = agent_session_repo.get_or_create_session(db, "seed", USER, None)
    db.commit()
    with patch("app.agent.harness.gateway.call", side_effect=AssertionError):
        r = harness.handle_chat(db, "seed", USER, "pay now", None, "seed-pay")
    assert r.status == "awaiting_confirmation", r
    with patch("app.agent.harness.gateway.call", side_effect=AssertionError):
        harness.handle_confirm(db, "seed", USER, True, "seed-confirm")
    from app.payments import wallet as wallet_service

    wallet_service.top_up(db, USER, 100_000, request_key="seed-topup")
    order = order_repo.list_by_user(db, USER, limit=1)[0]
    payment_service.pay_order(db, order, method="wallet", authorized_by="human_tap")
    db.commit()
    del sess


def reset_cart(db) -> None:
    from app.repositories import cart_repo

    cart = cart_repo.get_or_create_active_cart(db, USER)
    for item in list(cart.items):
        cart_service.delete_item(db, USER, item.id)
    cart_service.add_item(db, USER, CartItemCreate(sku="GRO-008", quantity=1))
    cart_service.add_item(db, USER, CartItemCreate(sku="GRO-004", quantity=2))
    db.commit()


def main() -> int:
    db = make_db()
    with patch("app.agent.harness.demand_capture.schedule_capture", lambda *a, **k: None):
        seed(db)
        ok = instant = 0
        for n, (lang, said, must, want_cart) in enumerate(PROBES, 1):
            reset_cart(db)
            sid = f"probe-{n}"
            calls = []

            def model_off(*a, **k):
                calls.append(1)
                raise RuntimeError("model off")

            agent_session_repo.get_or_create_session(db, sid, USER, None)
            agent_session_repo.get_session(db, sid).language = lang
            db.commit()
            with patch("app.agent.harness.gateway.call", side_effect=model_off):
                try:
                    r = harness.handle_chat(db, sid, USER, said, None, f"{sid}-1", language=lang)
                    reply = r.reply or ""
                except RuntimeError:
                    reply = ""
            if calls:
                print(f"[{n:2}] {lang} {said!r}\n      → MODEL   cart={cart_of(db)}")
                continue
            instant += 1
            good = any(m.lower() in reply.lower() for m in must)
            if want_cart is not None:
                good &= cart_of(db) == want_cart
            ok += good
            print(f"[{n:2}] {lang} {said!r}\n      {'OK ' if good else 'BAD'} {reply}"
                  + ("" if want_cart is None else f"   cart={cart_of(db)}"))
    print(f"\ninstant: {instant}/{len(PROBES)} · correct: {ok}/{len(PROBES)}")
    return 0 if ok == len(PROBES) else 1


if __name__ == "__main__":
    sys.exit(main())
