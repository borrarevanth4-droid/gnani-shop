"use client";

// The voice-first shop assistant — every Gnani Vachana feature the buyer
// sees lives here:
//   • Prisma v3.0 speech-to-text, auto language detection (indic-auto), 10 languages
//   • push-to-talk (REST) or a live conversation (realtime WebSocket)
//   • Timbre v3.0 / v2.5 voices, streamed so the reply starts speaking at once
//   • an "Under the hood" panel with Gnani's own timings for every turn
// Safety is unchanged from typed chat: the same agent and rulebook decide,
// and confirming or paying is always a tap on this screen, never a word.

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, Keyboard, Loader2, Mic, Radio, Send, ShieldCheck, Square, Volume2, VolumeX } from "lucide-react";
import {
  confirmPendingAction,
  fetchVoiceCatalog,
  sendAgentMessage,
  sendVoiceTurn,
  synthesizeStream,
  voiceStreamUrl,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { getOrCreateSessionId, startNewSessionId } from "@/lib/checkout";
import { LANGUAGES, nativeName, useI18n } from "@/lib/i18n";
import { MicRecorder, PcmPlayer } from "@/lib/voice";
import type { Cart, PaymentInfo, PaymentResult, PendingAction, VoiceCatalog, VoiceTurn } from "@/lib/types";
import PaymentSheet from "@/components/PaymentSheet";
import Button from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";

type Phase = "idle" | "listening" | "thinking" | "speaking";
type Mode = "ptt" | "live";

interface Turn {
  id: string;
  role: "user" | "assistant";
  text: string;
  language?: string | null;
  spoken?: string;
  meta?: Record<string, string | number | boolean | null | undefined>;
  blocked?: boolean;
}

const VOICE_PREF_KEY = "gnani-shop-voice";

export default function VoiceAssistant({ onCart, onPaid: onPaidOuter }: { onCart: (cart: Cart) => void; onPaid?: () => void }) {
  const { t, lang, setLang } = useI18n();
  const [catalog, setCatalog] = useState<VoiceCatalog | null>(null);
  const [mode, setMode] = useState<Mode>("ptt");
  const [phase, setPhase] = useState<Phase>("idle");
  const [level, setLevel] = useState(0);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [payment, setPayment] = useState<PaymentInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [typing, setTyping] = useState(false);
  const [text, setText] = useState("");
  const [speak, setSpeak] = useState(true);
  const [ttsModel, setTtsModel] = useState("timbre-v3.0");
  const [voice, setVoice] = useState("Shivani");
  const [openMeta, setOpenMeta] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState("");

  const recorder = useRef<MicRecorder | null>(null);
  const player = useRef<PcmPlayer | null>(null);
  const ws = useRef<WebSocket | null>(null);
  const muted = useRef(false); // live mode: don't send mic audio while Gnani is speaking
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    Promise.resolve().then(() => {
      setSessionId(getOrCreateSessionId());
      try {
        const saved = JSON.parse(window.localStorage.getItem(VOICE_PREF_KEY) ?? "null");
        if (saved?.model && saved?.voice) {
          setTtsModel(saved.model);
          setVoice(saved.voice);
        }
      } catch {
        // defaults
      }
    });
    fetchVoiceCatalog().then(setCatalog).catch(() => {});
    return () => {
      ws.current?.close();
      player.current?.stop();
    };
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(VOICE_PREF_KEY, JSON.stringify({ model: ttsModel, voice }));
    } catch {
      // ignore
    }
  }, [ttsModel, voice]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, phase]);

  const voicesForModel = (catalog?.tts[ttsModel]?.voices ?? []).filter(
    (v) => ttsModel === "timbre-v3.0" || !v.preferred_language || v.preferred_language === lang || (lang === "hi-IN" && v.preferred_language === "hi-en")
  );

  // ------------------------------------------------------------ speaking

  const say = useCallback(
    async (spokenText: string, language: string | null, metaId?: string) => {
      if (!speak || !spokenText.trim()) {
        setPhase("idle");
        return;
      }
      setPhase("speaking");
      muted.current = true;
      player.current?.stop();
      const p = new PcmPlayer();
      player.current = p;
      const done = new Promise<void>((resolve) => {
        p.onEnded = () => resolve();
      });
      try {
        const v = ttsModel === "timbre-v2.5" && !voicesForModel.some((x) => x.name === voice) ? undefined : voice;
        const { firstChunkMs } = await synthesizeStream(
          { text: spokenText, voice: v, model: ttsModel, language, sessionId },
          (pcm, rate) => p.enqueue(pcm, rate)
        );
        if (metaId) {
          setTurns((ts) =>
            ts.map((x) => (x.id === metaId ? { ...x, meta: { ...x.meta, "TTS model": ttsModel, Voice: v ?? "auto", "First audio": firstChunkMs != null ? `${firstChunkMs} ms` : "—" } } : x))
          );
        }
        await Promise.race([done, new Promise((r) => setTimeout(r, 30_000))]);
      } catch (e) {
        setError(`Speech unavailable: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        muted.current = false;
        setPhase((ph) => (ph === "speaking" ? (mode === "live" && ws.current ? "listening" : "idle") : ph));
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [speak, ttsModel, voice, sessionId, mode, lang, catalog]
  );

  // ------------------------------------------------------------ applying a turn

  function applyTurn(r: VoiceTurn | (Omit<VoiceTurn, "transcript" | "language" | "detected_language" | "gate_allowed" | "gate_rule" | "spoken_text" | "stt" | "fell_back_to_text" | "error"> & { spoken_text?: string }), userText: string | null, language: string | null) {
    const id = crypto.randomUUID();
    const isVoice = "gate_rule" in r;
    const meta: Turn["meta"] = isVoice
      ? {
          "STT model": (r as VoiceTurn).stt?.model ?? "prisma-v3.0",
          Format: (r as VoiceTurn).stt?.format ?? "transcribe",
          "Detected language": (r as VoiceTurn).detected_language ?? "—",
          "Gnani processing": (r as VoiceTurn).stt?.processing_time_ms != null ? `${(r as VoiceTurn).stt.processing_time_ms} ms` : "—",
          "Round trip": (r as VoiceTurn).stt?.round_trip_ms != null ? `${(r as VoiceTurn).stt.round_trip_ms} ms` : "—",
          "Voice gate": (r as VoiceTurn).gate_rule === "__default__" ? "allowed" : (r as VoiceTurn).gate_rule,
          "Agent status": r.status,
          ...(r.pending ? { "Rule that decided": r.pending.rule_name } : {}),
        }
      : { Channel: "typed", "Agent status": r.status, ...(r.pending ? { "Rule that decided": r.pending.rule_name } : {}) };
    setTurns((ts) => [
      ...ts,
      ...(userText ? [{ id: id + "-u", role: "user" as const, text: userText, language }] : []),
      {
        id,
        role: "assistant" as const,
        text: r.reply,
        spoken: r.spoken_text ?? r.reply,
        language,
        meta,
        blocked: isVoice && !(r as VoiceTurn).gate_allowed,
      },
    ]);
    onCart(r.cart);
    setPending(r.status === "awaiting_confirmation" ? r.pending : null);
    if (r.payment && r.payment.status === "AWAITING_PAYMENT") setPayment(r.payment);
    return id;
  }

  // ------------------------------------------------------------ push-to-talk

  async function startPtt() {
    setError(null);
    player.current?.stop();
    try {
      const rec = new MicRecorder(setLevel);
      await rec.start();
      recorder.current = rec;
      setPhase("listening");
    } catch {
      setError("Microphone permission is needed for voice. You can type instead.");
      setTyping(true);
    }
  }

  async function stopPtt() {
    const rec = recorder.current;
    recorder.current = null;
    if (!rec) return;
    const secs = rec.seconds();
    const wav = await rec.stop();
    if (secs < 0.4) {
      setPhase("idle");
      return;
    }
    setPhase("thinking");
    try {
      const r = await sendVoiceTurn(sessionId, wav, { ttsModel, languageHint: null });
      if (r.fell_back_to_text) {
        setTyping(true);
        applyTurn(r, null, r.language);
        setPhase("idle");
        return;
      }
      if (r.language) setLang(r.language);
      const id = applyTurn(r, r.transcript || "…", r.language);
      await say(r.spoken_text, r.language, id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("idle");
    }
  }

  // ------------------------------------------------------------ live conversation (realtime)

  async function startLive() {
    setError(null);
    const token = getToken();
    if (!token) return;
    const socket = new WebSocket(voiceStreamUrl({ token, session_id: sessionId, tts_model: ttsModel }));
    socket.binaryType = "arraybuffer";
    ws.current = socket;
    socket.onmessage = async (ev) => {
      const msg = JSON.parse(ev.data as string);
      if (msg.type === "ready") setPhase("listening");
      else if (msg.type === "processing") setPhase("thinking");
      else if (msg.type === "fallback") {
        setError(msg.message);
        stopLive();
        setTyping(true);
      } else if (msg.type === "error") setError(msg.message);
      else if (msg.type === "turn") {
        const r = msg as VoiceTurn;
        if (!r.transcript) {
          setPhase("listening");
          return;
        }
        if (r.language) setLang(r.language);
        const id = applyTurn(r, r.transcript, r.language);
        await say(r.spoken_text, r.language, id);
      }
    };
    socket.onclose = () => {
      ws.current = null;
      recorder.current?.stop();
      recorder.current = null;
      setPhase("idle");
    };
    try {
      const rec = new MicRecorder(setLevel, (pcm) => {
        if (!muted.current && socket.readyState === WebSocket.OPEN) socket.send(pcm.buffer);
      });
      await rec.start();
      recorder.current = rec;
    } catch {
      setError("Microphone permission is needed for voice.");
      socket.close();
    }
  }

  function stopLive() {
    try {
      ws.current?.send(JSON.stringify({ type: "stop" }));
    } catch {
      // closed already
    }
    ws.current?.close();
    ws.current = null;
    recorder.current?.stop();
    recorder.current = null;
    setPhase("idle");
  }

  function onMic() {
    if (mode === "live") {
      if (ws.current) stopLive();
      else startLive();
      return;
    }
    if (phase === "listening") stopPtt();
    else if (phase === "idle") startPtt();
    else if (phase === "speaking") {
      player.current?.stop();
      setPhase("idle");
    }
  }

  // ------------------------------------------------------------ typed + taps

  async function sendText() {
    const msg = text.trim();
    if (!msg) return;
    setText("");
    setPhase("thinking");
    setError(null);
    try {
      const r = await sendAgentMessage(sessionId, msg, null, lang);
      const id = applyTurn(r, msg, lang);
      await say(r.reply, lang, id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("idle");
    }
  }

  async function decide(approve: boolean) {
    setPhase("thinking");
    try {
      const r = await confirmPendingAction(sessionId, approve);
      applyTurn(r, null, lang);
      setPhase("idle");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("idle");
    }
  }

  function onPaid(r: PaymentResult) {
    setTurns((ts) => [
      ...ts,
      { id: crypto.randomUUID(), role: "assistant", text: r.status === "PAID" ? `${t("orderPlaced")} · #${r.order_id}` : `${t("codPlaced")} · #${r.order_id}`, language: lang },
    ]);
    setPending(null);
    onPaidOuter?.();
  }

  function newChat() {
    stopLive();
    setSessionId(startNewSessionId());
    setTurns([]);
    setPending(null);
  }

  // ------------------------------------------------------------ render

  const stateLabel =
    phase === "listening" ? (mode === "ptt" ? t("tapToStop") : t("listening")) : phase === "thinking" ? t("thinking") : phase === "speaking" ? t("speaking") : t("tapToSpeak");
  const live = mode === "live" && !!ws.current;

  return (
    <section className="gnani-hero overflow-hidden rounded-[20px] border border-line shadow-elevated">
      <div className="grid gap-0 lg:grid-cols-[minmax(0,420px)_1fr]">
        {/* Left: the mic */}
        <div className="flex flex-col items-center justify-between gap-6 border-b border-line p-8 lg:border-b-0 lg:border-r">
          <div className="w-full text-center lg:text-left">
            <Badge variant="voice" className="mb-3">
              <Radio size={12} className="mr-1" /> Powered by Gnani Vachana
            </Badge>
            <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">{t("heroTitle")}</h1>
            <p className="mt-2 text-sm leading-relaxed text-ink-soft">{t("heroSub")}</p>
          </div>

          <div className="flex flex-col items-center gap-3">
            <button
              onClick={onMic}
              disabled={phase === "thinking"}
              aria-label={stateLabel}
              className={`relative flex h-32 w-32 items-center justify-center rounded-full text-white transition-transform duration-150 active:scale-95 disabled:opacity-70 ${
                phase === "listening" || live ? "bg-voice voice-pulse" : phase === "speaking" ? "bg-accent" : "bg-voice shadow-voice hover:bg-voice-deep"
              }`}
            >
              <span
                className="absolute inset-0 rounded-full bg-voice/25 transition-transform duration-75"
                style={{ transform: `scale(${1 + level * 0.6})` }}
                aria-hidden
              />
              {phase === "thinking" ? (
                <Loader2 size={44} className="relative animate-spin" />
              ) : phase === "speaking" ? (
                <Volume2 size={44} className="relative" />
              ) : phase === "listening" || live ? (
                <Square size={36} className="relative" fill="currentColor" />
              ) : (
                <Mic size={48} className="relative" />
              )}
            </button>
            <p className="min-h-5 text-sm font-medium text-ink">
              {stateLabel}
              {phase === "thinking" && (
                <span className="ml-1 inline-flex gap-0.5">
                  <span className="voice-dot">·</span>
                  <span className="voice-dot [animation-delay:150ms]">·</span>
                  <span className="voice-dot [animation-delay:300ms]">·</span>
                </span>
              )}
            </p>

            <div className="flex rounded-full border border-line bg-surface p-0.5 text-xs">
              {(["ptt", "live"] as Mode[]).map((m) => (
                <button
                  key={m}
                  onClick={() => {
                    if (ws.current) stopLive();
                    setMode(m);
                  }}
                  className={`rounded-full px-3 py-1 font-medium transition ${mode === m ? "bg-ink text-white" : "text-ink-soft hover:text-ink"}`}
                >
                  {m === "ptt" ? t("pushToTalk") : t("realtime")}
                </button>
              ))}
            </div>
          </div>

          {/* language chips: the 10 Gnani languages, in their own scripts */}
          <div className="w-full">
            <p className="mb-2 text-center text-[11px] font-medium uppercase tracking-wide text-ink-faint lg:text-left">
              {t("language")} · auto-detected by Prisma v3.0
            </p>
            <div className="flex flex-wrap justify-center gap-1.5 lg:justify-start">
              {LANGUAGES.map((l) => (
                <button
                  key={l.code}
                  onClick={() => setLang(l.code)}
                  title={l.english}
                  className={`rounded-full border px-2.5 py-1 text-xs transition ${
                    lang === l.code ? "border-voice bg-voice-soft font-semibold text-voice-deep" : "border-line bg-surface text-ink-soft hover:border-line-strong"
                  }`}
                >
                  {l.native}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Right: the conversation */}
        <div className="flex min-h-[460px] flex-col bg-surface/70">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
            <div className="flex items-center gap-2 text-xs">
              <span className="text-ink-faint">{t("voice")}</span>
              <select
                value={ttsModel}
                onChange={(e) => {
                  setTtsModel(e.target.value);
                  if (e.target.value === "timbre-v3.0") setVoice("Shivani");
                }}
                className="rounded-md border border-line bg-surface px-2 py-1 text-xs"
              >
                <option value="timbre-v3.0">Timbre v3.0 · 13 voices × 10 languages</option>
                <option value="timbre-v2.5">Timbre v2.5 · 42 native voices</option>
              </select>
              <select value={voice} onChange={(e) => setVoice(e.target.value)} className="rounded-md border border-line bg-surface px-2 py-1 text-xs">
                {voicesForModel.map((v) => (
                  <option key={v.name} value={v.name}>
                    {v.name} {v.gender ? `(${v.gender[0]})` : ""} {v.preferred_language ? `· ${nativeName(v.preferred_language) || "Hinglish"}` : ""}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-1">
              <button onClick={() => setSpeak((s) => !s)} className="rounded-md p-1.5 text-ink-soft hover:bg-black/[0.04]" title={speak ? "Mute replies" : "Speak replies"}>
                {speak ? <Volume2 size={15} /> : <VolumeX size={15} />}
              </button>
              <Button size="sm" variant="ghost" onClick={newChat}>
                {t("newChat")}
              </Button>
            </div>
          </div>

          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4" style={{ maxHeight: 420 }}>
            {turns.length === 0 && (
              <div className="mx-auto mt-6 max-w-sm space-y-2 text-center text-sm text-ink-soft">
                <p className="font-medium text-ink">Try saying</p>
                {["2 किलो आटा और एक लीटर दूध चाहिए", "నాకు పాలు మరియు బ్రెడ్ కావాలి", "ஒரு டப்பா நெய் சேர்", "Add Maggi and a cold drink under ₹200"].map((s) => (
                  <p key={s} className="rounded-full border border-line bg-surface px-3 py-1.5 text-ink">
                    “{s}”
                  </p>
                ))}
              </div>
            )}
            {turns.map((turn) => (
              <div key={turn.id} className={`flex flex-col ${turn.role === "user" ? "items-end" : "items-start"}`}>
                <div
                  className={`max-w-[88%] whitespace-pre-wrap rounded-2xl px-3.5 py-2 text-sm leading-relaxed ${
                    turn.role === "user"
                      ? "rounded-br-sm bg-ink text-white"
                      : turn.blocked
                        ? "rounded-bl-sm border border-warning/30 bg-warning-soft text-warning"
                        : "rounded-bl-sm bg-black/[0.04] text-ink"
                  }`}
                >
                  {turn.text}
                </div>
                <div className="mt-1 flex items-center gap-2 px-0.5 text-[11px] text-ink-faint">
                  {turn.role === "user" ? t("youSaid") : "Gnani Shop"}
                  {turn.language && <span className="rounded-full bg-voice-soft px-1.5 text-voice-deep">{nativeName(turn.language)}</span>}
                  {turn.role === "assistant" && turn.spoken && (
                    <button className="hover:text-ink" onClick={() => say(turn.spoken!, turn.language ?? null)} title="Play again">
                      <Volume2 size={12} />
                    </button>
                  )}
                  {turn.meta && (
                    <button className="inline-flex items-center gap-0.5 hover:text-ink" onClick={() => setOpenMeta(openMeta === turn.id ? null : turn.id)}>
                      {t("underTheHood")} <ChevronDown size={11} className={openMeta === turn.id ? "rotate-180" : ""} />
                    </button>
                  )}
                </div>
                {turn.meta && openMeta === turn.id && (
                  <dl className="mt-1 grid max-w-[88%] grid-cols-2 gap-x-4 gap-y-1 rounded-md border border-line bg-surface px-3 py-2 font-mono text-[11px]">
                    {Object.entries(turn.meta).map(([k, v]) => (
                      <div key={k} className="contents">
                        <dt className="text-ink-faint">{k}</dt>
                        <dd className="text-ink">{String(v ?? "—")}</dd>
                      </div>
                    ))}
                  </dl>
                )}
              </div>
            ))}
          </div>

          {pending && (
            <div className="mx-4 mb-3 rounded-lg border border-warning/30 bg-warning-soft p-3">
              <p className="flex items-center gap-1.5 text-sm font-medium text-warning">
                <ShieldCheck size={15} /> {t("needsTap")}
              </p>
              <p className="mt-1 text-xs text-ink-soft">
                {pending.reason} <span className="font-mono">({pending.rule_name})</span>
              </p>
              <div className="mt-2 flex gap-2">
                <Button size="sm" variant="primary" onClick={() => decide(true)}>
                  {t("confirm")}
                </Button>
                <Button size="sm" variant="secondary" onClick={() => decide(false)}>
                  {t("decline")}
                </Button>
              </div>
            </div>
          )}

          {error && <p className="mx-4 mb-3 rounded-md bg-danger-soft px-3 py-2 text-xs text-danger">{error}</p>}

          <div className="border-t border-line p-3">
            {typing ? (
              <form
                className="flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  sendText();
                }}
              >
                <input
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="2 kg atta, 1 litre milk…"
                  className="flex-1 rounded-md border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-accent"
                />
                <Button type="submit" variant="primary" disabled={phase === "thinking" || !text.trim()}>
                  <Send size={14} /> {t("send")}
                </Button>
              </form>
            ) : (
              <button onClick={() => setTyping(true)} className="inline-flex items-center gap-1.5 text-xs text-ink-soft hover:text-ink">
                <Keyboard size={14} /> {t("typeInstead")}
              </button>
            )}
          </div>
        </div>
      </div>

      {payment && (
        <PaymentSheet
          payment={payment}
          onClose={() => setPayment(null)}
          onDone={(r) => {
            onPaid(r);
          }}
        />
      )}
    </section>
  );
}
