#!/usr/bin/env python
"""Live multilingual agent test — the real LLM, the real harness, the real rulebook.

    python eval/agent_live.py                 # all scenarios
    python eval/agent_live.py --only te_      # scenarios whose id starts with te_

Each scenario starts from a fresh in-memory shop (the real catalog), optionally
pre-fills the cart, sends one or more buyer messages exactly as a voice turn
would (with `language` and channel="voice"), then checks:

  cart      — the EXACT cart afterwards ({sku: quantity}); extra or missing items fail
  status    — e.g. "awaiting_confirmation" when the buyer asked to pay
  script    — the reply is written mostly in the buyer's own script

This is how the agent is "trained" here: we can't change the model's weights,
so we measure it on real commands in every language and fix what fails —
the instructions, the tools, the search — then measure again.
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "backend"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.agent import harness  # noqa: E402
from app.database import Base  # noqa: E402
from app.repositories import cart_repo, product_repo  # noqa: E402
from app.schemas.cart import CartItemCreate  # noqa: E402
from app.services import cart_service  # noqa: E402

USER = "user_live_eval"

# (id, language, messages, setup cart, expected cart, expected status or None)
SCENARIOS = [
    # --- single item, every language ------------------------------------------------
    ("te_milk", "te-IN", ["నాకు ఒక లీటర్ పాలు కావాలి"], {}, {"DAI-001": 1}, None),
    ("te_salt_two", "te-IN", ["రెండు ప్యాకెట్ల ఉప్పు వేయండి"], {}, {"GRO-004": 2}, None),
    ("hi_paneer", "hi-IN", ["एक पनीर का पैकेट डाल दो"], {}, {"DAI-005": 1}, None),
    ("ta_tea", "ta-IN", ["ஒரு பாக்கெட் டாடா டீ வேண்டும்"], {}, {"GRO-006": 1}, None),
    ("kn_biscuits", "kn-IN", ["ಎರಡು ಪಾರ್ಲೆ-ಜಿ ಬಿಸ್ಕತ್ ಸೇರಿಸಿ"], {}, {"BIS-001": 2}, None),
    ("ml_cola", "ml-IN", ["ഒരു കോക്ക കോള വേണം"], {}, {"DRI-001": 1}, None),
    ("mr_dal", "mr-IN", ["एक किलो तूर डाळ द्या"], {}, {"GRO-005": 1}, None),
    ("bn_tea", "bn-IN", ["এক প্যাকেট চা দিন"], {}, {"GRO-006": 1}, None),
    ("gu_ghee", "gu-IN", ["એક લીટર ઘી ઉમેરો"], {}, {"DAI-006": 1}, None),
    ("pa_milk_two", "pa-IN", ["ਦੋ ਲੀਟਰ ਦੁੱਧ ਪਾ ਦਿਓ"], {}, {"DAI-001": 2}, None),
    ("en_curd", "en-IN", ["Add one curd please"], {}, {"DAI-004": 1}, None),
    # --- several items in one sentence ----------------------------------------------
    ("te_multi", "te-IN", ["నాకు రెండు కిలోల ఆట్టా మరియు ఒక లీటర్ పాలు కావాలి"], {}, {"GRO-001": 1, "DAI-001": 1}, None),
    ("hi_multi", "hi-IN", ["दो पैकेट मैगी और एक पनीर डाल दो"], {}, {"GRO-008": 2, "DAI-005": 1}, None),
    ("ta_multi", "ta-IN", ["ஒரு லிட்டர் பால் மற்றும் ஒரு பாக்கெட் உப்பு வேண்டும்"], {}, {"DAI-001": 1, "GRO-004": 1}, None),
    ("en_multi", "en-IN", ["add 3 Maggi packets and a Coca-Cola"], {}, {"GRO-008": 3, "DRI-001": 1}, None),
    # --- code-mixed ------------------------------------------------------------------
    ("tinglish", "te-IN", ["naaku oka Amul butter and two Maggi packets add cheyyi"], {}, {"DAI-002": 1, "GRO-008": 2}, None),
    ("hinglish", "hi-IN", ["ek tata salt aur ek dahi add karo"], {}, {"GRO-004": 1, "DAI-004": 1}, None),
    ("tanglish", "ta-IN", ["oru packet Maggi add pannunga"], {}, {"GRO-008": 1}, None),
    # --- remove / change ---------------------------------------------------------------
    ("te_remove", "te-IN", ["ఉప్పు తీసేయండి"], {"DAI-001": 1, "GRO-004": 1}, {"DAI-001": 1}, None),
    ("hi_remove", "hi-IN", ["दूध हटा दो"], {"DAI-001": 1, "GRO-004": 1}, {"GRO-004": 1}, None),
    ("en_more", "en-IN", ["add one more milk"], {"DAI-001": 1}, {"DAI-001": 2}, None),
    # --- payment always asks the human ------------------------------------------------
    ("te_pay", "te-IN", ["ఇప్పుడు చెల్లించండి"], {"DAI-001": 1}, {"DAI-001": 1}, "awaiting_confirmation"),
    ("hi_pay", "hi-IN", ["अब पेमेंट कर दो"], {"GRO-004": 1}, {"GRO-004": 1}, "awaiting_confirmation"),
    # --- things we don't stock / can't do -----------------------------------------------
    ("te_unknown", "te-IN", ["నాకు మామిడి పండ్లు కావాలి"], {}, {}, None),
    ("hi_budget", "hi-IN", ["500 रुपये के अंदर बासमती चावल डाल दो"], {}, {}, None),
    ("ta_view", "ta-IN", ["என் கார்ட்டில் என்ன இருக்கு?"], {"DAI-001": 1}, {"DAI-001": 1}, None),
    # --- two-turn conversation ------------------------------------------------------------
    ("te_two_turns", "te-IN", ["ఒక లీటర్ పాలు", "ఇంకొకటి కూడా వేయండి"], {}, {"DAI-001": 2}, None),
    ("hi_two_turns", "hi-IN", ["एक दूध डालो", "एक और"], {}, {"DAI-001": 2}, None),
    # --- more languages × more commands --------------------------------------------------
    ("kn_remove", "kn-IN", ["ಹಾಲು ತೆಗೆದುಹಾಕಿ"], {"DAI-001": 1, "GRO-004": 1}, {"GRO-004": 1}, None),
    ("pa_remove", "pa-IN", ["ਲੂਣ ਹਟਾ ਦਿਓ"], {"DAI-001": 1, "GRO-004": 1}, {"DAI-001": 1}, None),
    ("ml_pay", "ml-IN", ["ഇനി പണം അടയ്ക്കാം"], {"DAI-001": 1}, {"DAI-001": 1}, "awaiting_confirmation"),
    ("bn_multi", "bn-IN", ["এক লিটার দুধ আর দুই প্যাকেট ম্যাগি দিন"], {}, {"DAI-001": 1, "GRO-008": 2}, None),
    ("gu_multi", "gu-IN", ["એક દહીં અને એક પનીર આપો"], {}, {"DAI-004": 1, "DAI-005": 1}, None),
    ("mr_multi", "mr-IN", ["दोन मॅगी आणि एक दूध द्या"], {}, {"GRO-008": 2, "DAI-001": 1}, None),
    ("ta_unknown", "ta-IN", ["எனக்கு ஆப்பிள் பழம் வேண்டும்"], {}, {}, None),
    ("en_atta_size", "en-IN", ["add 2 kg atta"], {}, {"GRO-001": 1}, None),
    ("hi_view", "hi-IN", ["मेरे कार्ट में क्या है?"], {"GRO-004": 2}, {"GRO-004": 2}, None),
]

SCRIPTS = {
    "hi-IN": (0x0900, 0x097F), "mr-IN": (0x0900, 0x097F), "bn-IN": (0x0980, 0x09FF), "pa-IN": (0x0A00, 0x0A7F),
    "gu-IN": (0x0A80, 0x0AFF), "ta-IN": (0x0B80, 0x0BFF), "te-IN": (0x0C00, 0x0C7F), "kn-IN": (0x0C80, 0x0CFF),
    "ml-IN": (0x0D00, 0x0D7F),
}


def script_share(text: str, lang: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    if lang == "en-IN":
        return sum(1 for c in letters if c.isascii()) / len(letters)
    lo, hi = SCRIPTS[lang]
    return sum(1 for c in letters if lo <= ord(c) <= hi) / len(letters)


def make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    catalog = json.loads((_ROOT / "backend" / "data" / "products.json").read_text(encoding="utf-8"))
    for e in catalog["products"]:
        product_repo.upsert(db, {k: e[k] for k in ("sku", "name", "brand", "category", "price_paise", "unit", "stock",
                                                    "description", "tags", "cost_paise")})
    db.commit()
    return db


def cart_of(db) -> dict[str, int]:
    cart = cart_repo.get_or_create_active_cart(db, USER)
    return {i.product.sku: i.quantity for i in cart.items}


def run(only: str | None) -> int:
    rows = []
    started = time.monotonic()
    with patch("app.agent.harness.demand_capture.maybe_capture", lambda *a, **k: None):
        for sid, lang, messages, setup, want_cart, want_status in SCENARIOS:
            if only and not sid.startswith(only):
                continue
            db = make_db()
            for sku, qty in setup.items():
                cart_service.add_item(db, USER, CartItemCreate(sku=sku, quantity=qty))
            t = time.monotonic()
            result = None
            error = None
            try:
                for m in messages:
                    result = harness.handle_chat(db, f"live-{sid}", USER, m, 500_000, f"live-{sid}", language=lang,
                                                 channel="voice")
            except Exception as e:  # noqa: BLE001
                error = str(e)[:200]
            secs = time.monotonic() - t
            got = cart_of(db)
            reply = (result.reply if result else "") or ""
            share = script_share(reply, lang)
            cart_ok = got == want_cart
            status_ok = want_status is None or (result is not None and result.status == want_status)
            script_ok = share >= 0.4 or not reply
            ok = cart_ok and status_ok and script_ok and error is None
            rows.append({
                "id": sid, "lang": lang, "messages": messages, "want_cart": want_cart, "got_cart": got,
                "want_status": want_status, "got_status": result.status if result else None, "reply": reply,
                "script_share": round(share, 2), "seconds": round(secs, 1), "passed": ok, "error": error,
                "fallback": any(s.get("fallback") for s in (result.steps if result else [])),
            })
            mark = "PASS" if ok else "FAIL"
            why = []
            if not cart_ok:
                why.append(f"cart {got} != {want_cart}")
            if not status_ok:
                why.append(f"status {result.status if result else None} != {want_status}")
            if not script_ok:
                why.append(f"reply script {share:.0%}")
            if error:
                why.append(f"error {error}")
            print(f"{mark} {sid:14} {secs:5.1f}s  {'; '.join(why)}")
            if not ok:
                print(f"       reply: {reply[:160]}")
            db.close()

    passed = sum(r["passed"] for r in rows)
    print(f"\n{passed}/{len(rows)} passed in {time.monotonic() - started:.0f}s")
    out = _ROOT / "eval" / "results" / f"agent_live_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"passed": passed, "total": len(rows), "rows": rows}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"saved {out.relative_to(_ROOT)}")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    sys.exit(run(ap.parse_args().only))
