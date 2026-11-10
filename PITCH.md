# Gnani Shop — Solution Pitch

**Voice-first grocery shopping in 10 Indian languages, built on Gnani Vachana.**
Revanth · Intern, Gnani AI · Code: [github.com/borrarevanth4-droid/gnani-shop](https://github.com/borrarevanth4-droid/gnani-shop)

## The problem

Shopping apps are built for people who type in English. Many Indians prefer their own language, mix languages as they speak, or find typing hard (elderly and first-time smartphone users). At a kirana store you just say what you need; apps make you do the opposite. People also worry that an AI could spend their money, leak their conversations, or answer things it shouldn't.

## The solution

Gnani Shop is a grocery store you talk to like a shopkeeper. Tap the mic once and speak in Hindi, English, Tamil, Telugu, Kannada, Malayalam, Marathi, Bengali, Gujarati or Punjabi, or mixed speech like Hinglish. It fills your cart, replies out loud in the same language, and listens again, hands-free. **Money only moves when a human taps.**

## How it works

- **Gnani Prisma v3.0** turns speech into text and detects the language automatically.
- **Gnani Timbre v3.0** speaks the reply, streamed, so it starts talking in about 0.9 seconds (13 voices, each speaks all 10 languages).
- **Instant path:** simple orders ("two kilo onions and a litre of milk") are parsed by exact code in all 10 languages, with no AI. Harder requests go to an AI model (Groq / NVIDIA).
- **"The AI suggests, the rulebook decides":** every action is checked by plain-code rules (budget, stock, limits), and every AI reply is checked for shop-only topics. Voice can fill a cart but can never pay.
- **Audit log:** every step is recorded in an append-only log, shown as "Harness loop" steps under each reply.

## Safety and privacy

- Each user's chats, voice, cart and orders are private to them; only approved shop-owner accounts can open the owner view.
- Off-topic questions are refused by ShopScopeRule, checked in code after every AI reply.
- Demo money only (wallet or cash on delivery), no real card or bank.

## Results (real test runs)

| Test | Result |
|---|---|
| Live spoken conversations, all 10 languages | 15 / 15 correct, replies in the right language |
| Multilingual order sentences on the instant path | 46 / 46 understood |
| Remove / question / pay sentences mistaken for "add" | 0 / 26 |
| Off-topic refused / shop questions allowed | 24 / 24 and 24 / 24 |
| Cross-user privacy attempts (second user targeting the first) | 14 / 14 blocked |
| Automated tests | 539 passing |

## Key features

Hands-free voice cart · mid-conversation language switching · voice remove and price questions · tap-to-pay checkout · cart history with "Buy again" and an add/remove timeline · Voice Lab (output formats, streaming vs whole-clip, voice gallery) · shop-owner insights and consented voice cloning.

## Tech

Gnani Vachana (Prisma v3.0 + Timbre v3.0) · Python FastAPI backend · Next.js frontend · Groq / NVIDIA models · Google sign-in.
