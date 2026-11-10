#!/usr/bin/env python
"""Live end-to-end VOICE test: Gnani speaks each command (Timbre), Gnani hears
it (Prisma, with the same language hint the app sends), then the real agent
and rulebook run — exactly the push-to-talk path of the app.

    python eval/voice_live.py

Checks, per command: the detected language, and the exact cart afterwards.
Uses Gnani credits (one TTS + one STT call per command) and the LLM.
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "backend"))
sys.path.insert(0, str(_ROOT / "eval"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from agent_live import USER, cart_of, make_db  # noqa: E402

from app.voice.gateway import voice_gateway  # noqa: E402
from app.voice.service import run_voice_turn  # noqa: E402

# (id, language, Timbre voice, spoken command, expected cart)
COMMANDS = [
    ("te", "te-IN", "Lakshmi", "నాకు ఒక లీటర్ పాలు మరియు రెండు ప్యాకెట్ల ఉప్పు కావాలి", {"DAI-001": 1, "GRO-004": 2}),
    ("tinglish", "te-IN", "Avinash", "naaku oka Amul butter add cheyyi", {"DAI-002": 1}),
    ("hi", "hi-IN", "Shivani", "दो पैकेट मैगी और एक पनीर डाल दो", {"GRO-008": 2, "DAI-005": 1}),
    ("ta", "ta-IN", "Prakash", "ஒரு லிட்டர் பால் வேண்டும்", {"DAI-001": 1}),
    ("kn", "kn-IN", "Chetana", "ಎರಡು ಪ್ಯಾಕೆಟ್ ಉಪ್ಪು ಸೇರಿಸಿ", {"GRO-004": 2}),
    ("ml", "ml-IN", "Kalpana", "ഒരു പാക്കറ്റ് ചായ വേണം", {"GRO-006": 1}),
    ("mr", "mr-IN", "Devansh", "एक किलो तूर डाळ द्या", {"GRO-005": 1}),
    ("bn", "bn-IN", "Riyaa", "এক লিটার দুধ দিন", {"DAI-001": 1}),
    ("gu", "gu-IN", "Harshad", "એક દહીં ઉમેરો", {"DAI-004": 1}),
    ("pa", "pa-IN", "Tarika", "ਦੋ ਲੀਟਰ ਦੁੱਧ ਪਾ ਦਿਓ", {"DAI-001": 2}),
    ("en", "en-IN", "Yashraj", "add three Maggi packets", {"GRO-008": 3}),
]


def main() -> int:
    rows, passed = [], 0
    with patch("app.agent.harness.demand_capture.schedule_capture", lambda *a, **k: None):
        for cid, lang, voice, text, want in COMMANDS:
            db = make_db()
            audio = voice_gateway.synthesize(text, voice=voice, language=lang, sample_rate=16000).audio
            t = time.monotonic()
            r = run_voice_turn(db, session_id=f"voice-{cid}", user_id=USER, audio=audio, budget_paise=500_000,
                               request_id=f"voice-{cid}", language_hint=lang)
            secs = time.monotonic() - t
            got = cart_of(db)
            ok = got == want and r.detected_language == lang
            passed += ok
            print(f"{'PASS' if ok else 'FAIL'} {cid:9} {secs:5.1f}s  heard [{r.detected_language}] {r.transcript}")
            if not ok:
                print(f"       cart {got} want {want}")
            print(f"       reply: {r.reply}")
            rows.append({"id": cid, "lang": lang, "said": text, "heard": r.transcript, "detected": r.detected_language,
                         "cart": got, "want": want, "reply": r.reply, "seconds": round(secs, 1), "passed": ok})
            db.close()
    print(f"\n{passed}/{len(COMMANDS)} passed")
    out = _ROOT / "eval" / "results" / f"voice_live_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    out.write_text(json.dumps({"passed": passed, "total": len(COMMANDS), "rows": rows}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    return 0 if passed == len(COMMANDS) else 1


if __name__ == "__main__":
    sys.exit(main())
