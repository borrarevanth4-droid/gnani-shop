# Engineering notes

Things that broke, things that were found and fixed, and decisions worth
explaining. Kept honest on purpose — the interesting part of a system that
handles money is what goes wrong.

## Found and fixed while building Gnani Shop

### 1. Agents could approve their own payments
The design rule is "a human approves anything the rulebook marks
REQUIRE_CONFIRMATION". But the confirm endpoint accepted agent keys, and a
confirmed agent payment was then completed automatically — so an agent could
pay on its own. **Fix:** an agent key may *decline* its own pending action but
never *approve* it (403). Autonomy now exists only as an explicit, owner-granted,
wallet-only, separately-limited **Mode B**, decided inside the rulebook by
`AgentAutopayRule` and recorded as `authorized_by=agent_autopay`.
Tests: `tests/test_payments.py`.

### 2. An agent's own items were counted twice at payment
Items an agent adds are reserved against its spend limit immediately. At payment,
`PaymentAuthorizationRule` replays every cart line through the item rules — on top
of that reservation. A ₹60 cart under a ₹100 limit was refused at payment.
**Fix:** the replay starts from the agent's spend *outside* this cart, so its
exposure is `max(already reserved, cart total)`. Regression test:
`test_agent_payment_is_not_double_counted_against_its_spend_limit`.

### 3. Removing an item never gave an agent its budget back
**Fix:** `_maybe_release_agent_spend` releases the removed line's reservation
(never more than was reserved).

### 4. Several agents could add up to more than any one limit
Three agents at ₹500 each were ₹1,500 of exposure no rule saw.
**Fix:** `AccountSpendLimitRule` sums every agent the owner has.

### 5. The injection scanner only knew English
"पिछले निर्देश भूल जाओ" would not have been flagged. **Fix:** native-script
phrasings in all 10 languages plus romanised Hinglish; voice transcripts are
scanned too (`SpokenInjectionRule`). The real guarantee is still structural — the
rulebook re-checks every action — the scanner makes attempts visible.

### 6. A defaulting fix that turned 0 into 1 (caught by the eval)
Groq validates tool arguments strictly and sends `null` for an omitted optional
quantity, so the parser was changed to default to 1 — written as
`quantity or 1`, which also turned an explicit **0** into **1**. The safety eval's
`edge_zero_quantity` scenario caught it as a false negative. **Fix:** only a
missing/`null` quantity defaults to 1. Test:
`test_null_quantity_defaults_to_one_but_zero_is_rejected`.

### 7. A wrong category guess hid products we stock
Live, the model searched for milk with `category="groceries"`; milk is `dairy`.
**Fix:** the tool schema lists the real categories, and a zero-result search with a
category is retried without it (deterministic, and noted in the tool result).
Search also falls back to the significant words of a phrase ("milk 1 litre").

### 8. "OK, pay now" accepted an upsell
Live in Telugu, "సరే, ఇప్పుడు చెల్లించండి" ("OK, now pay") was read as accepting the
offered cold drink before paying. Nothing was charged — the payment still needed
a tap and the total was read back — but the prompt now states that a bare "ok"
followed by checkout is a *decline*.

### 9. Gnani's edge rejected the default Python User-Agent
`error code: 1010` (Cloudflare) on the first raw call. **Fix:** the gateway sends
an honest `gnani-shop/1.0` User-Agent on every request, REST and WebSocket.

### 10. Free-tier rate limits
Groq's free tier allows 8,000 tokens/minute; a multi-step agent turn uses ~2,000
per model call. **Fix:** the LLM gateway now waits for the provider's own
"try again in Xs" hint (capped at 12 s) instead of a fixed 1–2 s backoff, then
falls back to the smaller model. A paid tier or `LLM_PROVIDER=nvidia` removes the
wait.

### 11. Product cards could never be shown (inherited bug)
The agent's `present_product` tool had no case in the argument parser, so every
call was rejected as "malformed" and the model retried until the 8-step limit.
Found live on a Tamil voice turn in Docker ("one litre of milk"). **Fix:** a parser
case, plus a test that every tool schema the model is offered has one
(`test_every_tool_schema_has_a_parser_case`).

### 12. Short Telugu words were heard as Malayalam
With pure `indic-auto`, "పాలు" (milk) and "ఉప్పు" (salt) came back as Malayalam
"പാലും" / "ഉപ്പ്" — a few syllables are not much to identify a language from.
**Fix:** Prisma v3.0 accepts 1–4 language codes as *hints* (not a lock), so the
buyer's chosen language is sent first plus English (`te-IN,en-IN`), which also
covers code-mixed speech (Tinglish/Hinglish). Measured live: both words then
transcribed correctly in Telugu; with no chosen language we still use
`indic-auto` (`app/voice/hints.py`).

### 13. First syllable clipped
A clip that starts the instant speech starts lost its first consonant
("పాలు" → "ఆలు"). **Fix:** 0.3 s of silence is prepended before sending to
Prisma (`pad_leading_silence`); reported audio length excludes it.

### 14. One provider's rate limit stalled every turn
Benchmarked on our own Telugu / Tinglish / Hindi prompts: Groq `gpt-oss-120b`
was the most accurate and fastest (0.5–1.4 s per step); of the NVIDIA models
this key can reach, only `nemotron-3.5-lightning` answered tool calls in time
(~5 s), several others returned 404 or timed out. **Fix:** the fallback model
can live on a different provider (`LLM_FALLBACK_PROVIDER=nvidia`), and a 429
with a long wait now hands the turn to the fallback immediately instead of
sleeping.

## Decisions

- **No card gateway.** Demo wallet + Cash on Delivery behind a provider slot.
  The wallet balance is derived from an append-only ledger, never stored.
- **Raw audio is never stored.** Only the transcript the agent acted on.
- **Tags only from templates.** The model can't make the voice whisper or shout.
- **Fixed phrases for money moments.** "Your total is ₹245, tap to confirm" is a
  reviewed string in each language, not model output.
- **Dictionary, not AI, for multilingual search.** Exact, instant, free, testable.

## Known limits

- In-memory rate limiter: correct for one process only.
- The 10-language phrases and vocabulary were written carefully but should be
  reviewed by native speakers before real use.
- Realtime voice is half-duplex: the mic is muted while Gnani is speaking, so you
  can't interrupt the assistant mid-sentence (tap the mic to stop it instead).
