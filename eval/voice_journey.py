#!/usr/bin/env python
"""Voice journeys — testing like a real person talking to the shop.

    python eval/voice_journey.py
    python eval/voice_journey.py --only te

Each journey is a whole spoken conversation (order → one more → remove →
what's in my cart → pay). For every turn:

  1. Gnani Timbre speaks the buyer's sentence (a real voice, real audio)
  2. the app's voice pipeline runs: Prisma hears it → voice gate → agent → rulebook
  3. Gnani Timbre speaks the assistant's reply, streamed exactly like the app
  4. Gnani Prisma LISTENS to that reply and we check what a person would notice:
       - did the reply audio contain the whole reply?          (completeness)
       - was all of it heard in the buyer's language?          (no language switch)
       - how long until the buyer heard the first word?         (latency)

and at the end the cart must be exactly right.
"""

import argparse
import difflib
import io
import json
import re
import statistics
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "backend"))
sys.path.insert(0, str(_ROOT / "eval"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from agent_live import SCRIPTS, USER, cart_of, make_db  # noqa: E402

from app.repositories import agent_session_repo  # noqa: E402
from app.voice.gateway import voice_gateway  # noqa: E402
from app.voice.hints import stt_language_code  # noqa: E402
from app.voice.service import run_voice_turn  # noqa: E402

RATE = 24000

# (id, language, buyer voice, reply voice, [turns], expected final cart, last turn should await a tap?)
JOURNEYS = [
    ("te", "te-IN", "Lakshmi", "Shivani", [
        "నాకు ఒక లీటర్ పాలు మరియు రెండు ప్యాకెట్ల ఉప్పు కావాలి",
        "ఇంకో పాలు కూడా వేయండి",
        "ఉప్పు తీసేయండి",
        "నా కార్ట్‌లో ఏముంది?",
        "ఇప్పుడు చెల్లించండి",
    ], {"DAI-001": 2}, True),
    ("kirana", "te-IN", "Lakshmi", "Shivani", [
        "రెండు కిలోల ఉల్లిపాయలు, ఆరు గుడ్లు మరియు ఒక కిలో చక్కెర కావాలి",
        "ఇంకా ఏమేమి ఉన్నాయి?",
        "ఒక బ్రెడ్ కూడా వేయండి",
        "హిందీలో మాట్లాడు",
        "एक किलो टमाटर डाल दो",
    ], {"KIR-008": 2, "KIR-011": 1, "KIR-004": 1, "KIR-012": 1, "KIR-009": 1}, False),
    ("hi", "hi-IN", "Avinash", "Shivani", [
        "मुझे दो पैकेट मैगी और एक पनीर चाहिए",
        "एक दूध भी डाल दो",
        "मैगी हटा दो",
        "अब पेमेंट कर दो",
    ], {"DAI-005": 1, "DAI-001": 1}, True),
    ("tinglish", "te-IN", "Avinash", "Shivani", [
        "naaku oka Amul butter and two Maggi packets add cheyyi",
        "inko butter kuda add cheyyi",
    ], {"DAI-002": 2, "GRO-008": 2}, False),
    ("ta", "ta-IN", "Prakash", "Lakshmi", [
        "ஒரு லிட்டர் பால் மற்றும் ஒரு பாக்கெட் டீ வேண்டும்",
        "டீ வேண்டாம், அதை நீக்குங்கள்",
        "என் கார்ட்டில் என்ன இருக்கு?",
    ], {"DAI-001": 1}, False),
    ("kn", "kn-IN", "Chetana", "Shivani", [
        "ಎರಡು ಪಾರ್ಲೆ-ಜಿ ಬಿಸ್ಕತ್ ಮತ್ತು ಒಂದು ಹಾಲು ಸೇರಿಸಿ",
        "ಹಣ ಪಾವತಿಸಿ",
    ], {"BIS-001": 2, "DAI-001": 1}, True),
    ("en", "en-IN", "Yashraj", "Shivani", [
        "add three Maggi packets and a Coca-Cola",
        "actually remove the Coca-Cola",
        "do you have mangoes?",
    ], {"GRO-008": 3}, False),
]


def to_wav(pcm: bytes, rate: int = RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def letters(text: str) -> str:
    return re.sub(r"[^\w]", "", text.lower(), flags=re.UNICODE)


def native_share(text: str, lang: str) -> float:
    ls = [c for c in text if c.isalpha()]
    if not ls:
        return 1.0
    if lang == "en-IN":
        return sum(c.isascii() for c in ls) / len(ls)
    lo, hi = SCRIPTS[lang]
    return sum(lo <= ord(c) <= hi for c in ls) / len(ls)


def run(only: str | None) -> int:
    rows = []
    ok_journeys = 0
    started = time.monotonic()
    with patch("app.agent.harness.demand_capture.schedule_capture", lambda *a, **k: None):
        for jid, lang, buyer_voice, reply_voice, turns, want_cart, want_pending in JOURNEYS:
            if only and not jid.startswith(only):
                continue
            db = make_db()
            sid = f"journey-{jid}-{int(time.time())}"
            print(f"\n=== {jid} ({lang}) ===")
            journey_ok = True
            last = None
            for i, said in enumerate(turns, 1):
                audio = voice_gateway.synthesize(said, voice=buyer_voice, language=lang, sample_rate=16000).audio
                t0 = time.monotonic()
                r = run_voice_turn(db, session_id=sid, user_id=USER, audio=audio, budget_paise=500_000,
                                   request_id=f"{sid}-{i}", language_hint=lang)
                t_turn = time.monotonic() - t0
                last = r
                lang = r.language or lang  # "speak Hindi" — the reply (and the buyer) switch language
                # speak the reply exactly like the app (streamed)
                t1 = time.monotonic()
                first = None
                pcm = bytearray()
                for c in voice_gateway.synthesize_stream(r.spoken_text, voice=reply_voice, language=lang,
                                                          sample_rate=RATE):
                    if c.audio and first is None:
                        first = time.monotonic() - t1
                    pcm.extend(c.audio)
                audio_secs = len(pcm) / 2 / RATE
                # listen to the reply like the buyer would
                heard = voice_gateway.transcribe(to_wav(bytes(pcm)), language=stt_language_code(lang))
                sim = difflib.SequenceMatcher(None, letters(r.spoken_text), letters(heard.transcript)).ratio()
                lang_ok = (heard.detected_language == lang) or lang == "en-IN"
                share = native_share(heard.transcript, lang)
                complete = sim >= 0.55
                pure = lang_ok and share >= 0.6
                to_first_sound = t_turn + (first or 0)
                ok = complete and pure and r.gate_allowed is not False or not r.transcript
                flags = []
                if not complete:
                    flags.append(f"INCOMPLETE (match {sim:.0%})")
                if not pure:
                    flags.append(f"LANGUAGE SWITCH (heard {heard.detected_language}, native {share:.0%})")
                print(f"[{i}] buyer: {said}")
                print(f"    heard as: {r.transcript} [{r.detected_language}]")
                print(f"    reply   : {r.spoken_text}")
                print(f"    spoken  : {heard.transcript}")
                print(f"    timing  : turn {t_turn:.1f}s + first sound {first or 0:.1f}s = {to_first_sound:.1f}s · "
                      f"audio {audio_secs:.1f}s  {'OK' if not flags else ' | '.join(flags)}")
                journey_ok &= not flags
                rows.append({"journey": jid, "turn": i, "said": said, "heard": r.transcript,
                             "detected": r.detected_language, "reply": r.spoken_text, "reply_heard": heard.transcript,
                             "match": round(sim, 2), "reply_lang": heard.detected_language,
                             "turn_s": round(t_turn, 2), "first_sound_s": round(first or 0, 2),
                             "to_first_sound_s": round(to_first_sound, 2), "audio_s": round(audio_secs, 1),
                             "flags": flags})
            got = cart_of(db)
            pending = bool(last and last.status == "awaiting_confirmation")
            cart_ok = got == want_cart
            pend_ok = pending == want_pending
            print(f"    FINAL cart {got} {'✓' if cart_ok else '✗ want ' + str(want_cart)}"
                  f" · awaiting tap {pending} {'✓' if pend_ok else '✗'}")
            journey_ok &= cart_ok and pend_ok
            ok_journeys += journey_ok
            db.close()
    total = len({r["journey"] for r in rows})
    tts = [r["to_first_sound_s"] for r in rows]
    print(f"\n{ok_journeys}/{total} journeys perfect · {sum(not r['flags'] for r in rows)}/{len(rows)} turns clean")
    if tts:
        print(f"time to first sound: median {statistics.median(tts):.1f}s, worst {max(tts):.1f}s "
              f"({time.monotonic() - started:.0f}s total)")
    out = _ROOT / "eval" / "results" / f"voice_journey_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    out.write_text(json.dumps({"journeys_ok": ok_journeys, "journeys": total, "rows": rows}, ensure_ascii=False,
                              indent=2), encoding="utf-8")
    return 0 if ok_journeys == total else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    sys.exit(run(ap.parse_args().only))
