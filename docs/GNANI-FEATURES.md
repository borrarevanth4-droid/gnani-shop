# Gnani Vachana features used in Gnani Shop

Every Gnani speech capability this project uses, where it lives in the code, and
where you can see it in the app. Model names and limits are from
[docs.gnani.ai](https://docs.gnani.ai).

## Speech to text — Prisma

| Gnani feature | How Gnani Shop uses it | Code | See it |
|---|---|---|---|
| **Prisma v3.0** (`prisma-v3.0`) | Every voice turn | `app/voice/gateway.py::transcribe` | Shop mic |
| **Auto language detection** (`language_code=indic-auto`) | No language picker; `detected_language_code` becomes the conversation's language | `app/voice/service.py` | Language chip on each turn |
| **10 languages** (hi, en, ta, te, kn, ml, mr, bn, gu, pa) + code-mixed Hinglish | All of them, end to end | `app/voice/languages.py` | Language chips |
| **Output formats** (`transcribe`, `verbatim`, `codemix`, `transliterate`) | `transcribe` in the shop, so "दो किलो" arrives as the digit **2** | `GNANI_STT_FORMAT` | Voice Lab §1 compares all four |
| **Keyterms** (≤200) | Brand & product names from the catalog, so "Aashirvaad", "Amul" are heard right | `app/voice/keyterms.py` | Voice Lab §1 compares on/off |
| **Context** (`topic`, `previous_text`) | "Grocery shopping" topic + the assistant's last reply, so "add one more" works | `app/voice/service.py` | — |
| **Realtime WebSocket** (`/stt/v3/stream`, 1024-byte PCM frames, `commit`) | Live conversation mode, bridged server-side | `app/voice/realtime.py` | Shop → "Live conversation" |
| **Timings** (`processing_time`, `end_to_end_latency`) | Shown per turn and aggregated for merchants | audit `voice_transcribed` | "Under the hood"; Merchant → Voice Insights |
| **Batch transcription + speaker separation** | Phone-order recordings → transcripts → demand alerts | `app/voice/gateway.py::batch_*`, `app/routers/merchant_voice.py` | Merchant → Voice → Call Insights |

## Text to speech — Timbre

| Gnani feature | How Gnani Shop uses it | Code | See it |
|---|---|---|---|
| **Timbre v3.0** — 13 voices, every voice speaks all 10 languages | Default reply voice ("Shivani"); one persona follows the buyer across languages | `app/voice/languages.py` | Voice picker; Voice Lab §3 gallery |
| **Timbre v2.5** — 42 native voices, Hinglish "Poorvi" | Alternative "native voice" mode, auto-matched to the language | `app/routers/voice.py::_resolve_voice` | Voice picker |
| **SSE streaming** (`/api/v1/tts/sse`) | Replies start playing on the first chunk | `gateway.synthesize_stream`, `lib/voice.ts::PcmPlayer` | Voice Lab §2 measures first-audio time |
| **Sync synthesis** (`/api/v1/tts/inference`) | Product read-outs, Voice Lab comparison | `gateway.synthesize` | Voice Lab §2 |
| **Audio tags** (13, v3.0 only) | `<excited>` on "order placed", `<pauses>` before an amount — from templates only | `app/voice/spoken.py` | Voice Lab tag buttons |
| **Text normalisation** (₹, lakh grouping, IDs read digit by digit) | Amounts sent as "₹173.50" and read correctly in every language | — | Any reply with a price |
| **Explicit language codes** | Always sent, because `auto` reads Marathi Devanagari as Hindi | `_resolve_voice` | — |

## Voice cloning

| Gnani feature | How Gnani Shop uses it | Code | See it |
|---|---|---|---|
| **Embeddings** (`/api/v1/tts/voice-clone/embeddings`, 5–30 s) | Merchant's "Shop Voice", created only with consent | `gateway.clone_embedding` | Merchant → Voice → Shop Voice |
| **`vachana-vc-v1` synthesis** | Speak offers in the shop owner's own voice | `gateway.synthesize(speaker_embedding=…)` | "Speak in my voice" |

## Engineering around Gnani (same patterns as the LLM)

- **One gateway** — nothing else calls `api.vachana.ai`.
- **Retry** only on 429 / 5xx / timeouts; a bad key or bad input is never retried.
- **Circuit breaker** per capability (speech-to-text, text-to-speech) → instant fall-back to typing.
- **Chaos faults** for Gnani: `GNANI_STT_TIMEOUT`, `GNANI_TTS_FAILURE`, `GNANI_GARBLED_TRANSCRIPT`.
- **User-Agent** set explicitly — Gnani's edge rejects generic library agents (`error code: 1010`).
- **Cost accounting** hooks (`GNANI_COST_PAISE_PER_AUDIO_SECOND`, `…_PER_TTS_CHAR`) on every audit event.
- **Rate limiting** per user on every endpoint that spends Gnani credits.

## Not used (yet)

- Gnani's **Agent Builder / Inya platform**, **LiveKit / Pipecat plugins** and the
  **`gnani-vachana` Python SDK** — this project talks to the REST/WebSocket APIs
  directly through its own gateway so the retry/breaker/audit behaviour is
  identical to the LLM side. Any of them could be added behind the same gateway.
