# Gnani Shop

**A grocery store you can talk to — in any of 10 Indian languages.**

Speak Hindi, Tamil, Telugu, Kannada, Malayalam, Marathi, Bengali, Gujarati,
Punjabi, English or Hinglish. **Gnani Vachana** hears you and works out which
language you're speaking. An AI shop assistant fills your cart and answers you
in that language, in a natural voice. **Nothing is ever paid until you tap.**

Built by **Revanth** (borrarevanth4@gmail.com) to showcase Gnani's speech models
— Prisma v3.0 (speech → text), Timbre v3.0 / v2.5 (text → speech) and
voice cloning — inside a commerce system engineered so that an AI can help
with your money but never take control of it.

---

## The idea, in one line

> **Gnani hears and speaks. The AI suggests. The rulebook decides. The diary remembers.
> Only a human tap moves money.**

```
 🎤 you speak ─▶ 👂 Gnani Prisma ─▶ 🧠 AI suggests ─▶ 📕 rulebook decides ─▶ ✋ cart / orders
                  (text + language)    (Groq / NVIDIA)    (plain Python)
 🔊 you hear  ◀── 👄 Gnani Timbre ◀── reply in your language          📓 every step → audit diary
```

---

## Run it in two minutes

You need **Docker** and two keys.

```bash
cp .env.example .env        # add GNANI_API_KEY and GROQ_API_KEY (or NVIDIA_API_KEY)
docker compose up --build
```

Open **http://127.0.0.1:3000** → **Continue as Demo Buyer** → tap the orange mic and
say *"दो किलो आटा और एक लीटर दूध चाहिए"* — or anything, in any of the 10 languages.

> Use `127.0.0.1`, not `localhost` (they are different origins for sign-in).
> Browsers only allow the microphone on `127.0.0.1`/`localhost` or HTTPS — for a
> phone, put the frontend behind an HTTPS tunnel (e.g. ngrok).

| | |
|---|---|
| Shop + dashboards | http://127.0.0.1:3000 |
| API | http://127.0.0.1:8842 |
| Voice Lab (all Gnani features side by side) | http://127.0.0.1:3000/voice-lab |
| Agent-readable catalog | http://127.0.0.1:8842/.well-known/catalog.json |

### Without Docker

```bash
python -m venv venv && venv/Scripts/pip install -r backend/requirements.txt   # Windows
cd backend && ../venv/Scripts/python scripts/seed.py && cd ..
cd frontend && npm install && npm run app     # or double-click start.bat
```

`npm run app` starts the API and the shop together; everything is served from
**http://127.0.0.1:3000** (the shop forwards `/api/*` to the API on port 8842).
Ctrl+C stops both.

Check voice accuracy in all 10 languages with real Gnani audio:
`venv/Scripts/python eval/voice_journey.py` (15 spoken conversations).

---

## What you can do

**As a buyer**
- 🎤 **Voice Shop** — push-to-talk or a live conversation; the language is detected
  automatically; pick from 13 Timbre v3.0 voices (each speaks all 10 languages) or
  42 native Timbre v2.5 voices; "Under the hood" shows Gnani's own timings per turn.
- 🛒 Browse with product names in your language (search "పాలు", "आटा" or "milk").
- 💳 Pay with the **Gnani Shop Wallet** (demo money) or **Cash on Delivery** — always a tap.
- 🤖 Give an agent a key with its own spending limit. It can fill a cart and ask to pay;
  you approve. Optionally switch on **autopay (Mode B)** for that one agent, wallet only,
  with its own limit.
- 🧪 **Voice Lab** — the same recording in all four Prisma output formats, with and
  without catalog keyterms; streaming vs. whole-clip speech; audio tags; the voice gallery.

**As a merchant**
- 📊 **Voice Insights** — which languages customers speak, Gnani latency, how often
  voice fell back to text, what the voice gate refused.
- 🎙️ **Shop Voice** — clone your own voice (with consent) to speak offers.
- 📞 **Call Insights** — upload phone-order recordings; Gnani batch-transcribes them with
  speaker separation; requests become anonymous "N buyers asked for X" alerts.
- Campaigns with control groups and margin guardrails, demand alerts, product
  controls, and a step-by-step **replay of any conversation** from the audit log.

---

## Safety, by construction

| Guarantee | Why it holds |
|---|---|
| **Voice can't pay** | The voice endpoints only call the chat harness; approving and paying are separate tap endpoints. A test checks the voice code never imports them |
| **An agent can't approve its own payment** | `/api/agent/confirm` refuses `approve=true` from an agent key. Autopay exists only as an owner-granted, wallet-only, limited Mode B |
| **The payment rule never says "allow"** | `PaymentAuthorizationRule` has no ALLOW path — only "ask the human" or "refuse" |
| **No double charge** | A wallet debit is keyed by order id under a database UNIQUE constraint |
| **The audit log can't be edited** | Its repository has no update or delete function |
| **Spoken tricks don't reach the agent** | "Forget the rules" in 10 languages + Hinglish is stopped by the voice gate |
| **The voice can't be made to shout or whisper by the AI** | Model-written audio tags are stripped; only fixed templates add them |
| **Demo logins and fault injection don't exist in production** | Gated on `APP_ENV=development` in code |

---

## Numbers (real output, nothing estimated)

**Tests** — `cd backend && ../venv/Scripts/python -m pytest -q`

**367 passed** — including 46 voice tests (Gnani mocked), 18 payment / Mode A-B tests and
13 multi-language search tests.

**Safety eval** — `python eval/run.py --stub` (deterministic: pins the rulebook)

| Run | Scenarios | Passed | False positives | False negatives |
|---|---|---|---|---|
| Stub model | 41 (28 original + 13 multi-language) | **41** | 0 | 0 |

The live-model eval (`python eval/run.py`) works too, but on Groq's free tier
(8,000 tokens/minute) 41 scenarios take a long time; run it on a paid tier or NVIDIA.

**Live agent test** — `python eval/agent_live.py` (real LLM + harness + rulebook, checks the exact cart,
status and reply script): **37/37** commands across all 10 languages + Tinglish / Hinglish / Tanglish —
add, multi-item, quantities, remove, "one more", view cart, pay, budget, unknown products, two-turn chats.
(Baseline before tuning: 10/27 — see docs/ENGINEERING-NOTES.md §15.)

**Live voice test** — `python eval/voice_live.py` (Gnani Timbre speaks → Gnani Prisma hears → agent):
**11/11**, every language detected correctly and every cart exact.

**Live Gnani, measured in this build** (Telugu & Hindi, push-to-talk, from India):
Prisma v3.0 model processing ≈ 0.17–0.25 s, round trip ≈ 1.2–1.5 s; Timbre streaming
first audio ≈ 1.0 s; whole-clip synthesis ≈ 1.3–1.8 s. The slow part of a voice turn
is the LLM on a free tier, not Gnani: on Groq's free plan a multi-step turn can wait
tens of seconds for token quota.

---

## Docs

| | |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How it all fits together, the rulebook, Mode A/B, resilience, privacy |
| [docs/GNANI-FEATURES.md](docs/GNANI-FEATURES.md) | Every Gnani Vachana feature used, where in the code, where in the app |
| [docs/ENGINEERING-NOTES.md](docs/ENGINEERING-NOTES.md) | What broke, what was fixed, honest limits |

## Repository map

```
backend/            FastAPI · agent harness · policy engine · Gnani voice layer · audit
  app/voice/          Gnani gateway, realtime bridge, voice gate, spoken text, languages
  app/payments/       provider slot · wallet ledger · cash on delivery
  app/i18n/           grocery vocabulary in 10 languages
frontend/           Next.js — Voice Shop, Voice Lab, wallet, agents, merchant voice
eval/               Safety evaluation (41 scenarios)
integration-demo/   A third-party shop with no AI of its own, shopping through the API
buyer_agent/        A headless agent that shops with an issued key
campaigns/          Campaign orchestrator
demo.py             Scripted walkthrough of everything above
```

## Environment

| Variable | For | Without it |
|---|---|---|
| `GNANI_API_KEY` | Voice (Prisma, Timbre, cloning, batch) | Voice says "please type"; everything else works |
| `LLM_PROVIDER` + `GROQ_API_KEY` / `NVIDIA_API_KEY` | The shop assistant | Chat returns an error; browsing and buying work |
| `GOOGLE_CLIENT_ID/SECRET` | Signing in as yourself | Use the demo accounts |
| `JWT_SECRET_KEY` | Signing this app's tokens | Required |
| `APP_ENV` | `development` enables demo login + chaos | Anything else disables both |

All money in Gnani Shop is **demo money**. No card, bank or payment network is involved.
