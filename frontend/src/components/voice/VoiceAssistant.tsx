"use client";

// The voice-first shop assistant — a full-bleed dark band.
//
// Hands-free by default: one press starts listening; the browser detects
// when you stop talking (a simple energy-based voice-activity detector) and
// sends the clip; Gnani Prisma transcribes it with your language as a hint;
// the agent harness proposes, the rulebook decides; Gnani Timbre speaks the
// reply; then it listens again. Click the mic while listening to stop early,
// click while it's speaking (or "End") to finish the conversation.
//
// Confirming and paying are always taps on the screen, never words.

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, Keyboard, Loader2, Mic, Send, ShieldCheck, Square, Volume2, VolumeX } from "lucide-react";
import { confirmPendingAction, fetchVoiceCatalog, sendAgentMessage, sendVoiceTurn, synthesizeStream } from "@/lib/api";
import { getOrCreateSessionId, startNewSessionId } from "@/lib/checkout";
import { LANGUAGES, nativeName, useI18n } from "@/lib/i18n";
import { DEFAULT_VAD, MicRecorder, PcmPlayer, VoiceActivityDetector, unlockAudio } from "@/lib/voice";
import type { Cart, PaymentInfo, PaymentResult, PendingAction, VoiceCatalog, VoiceTurn } from "@/lib/types";
import PaymentSheet from "@/components/PaymentSheet";
import Button from "@/components/ui/Button";

type Phase = "idle" | "listening" | "thinking" | "speaking";

export interface HarnessStep {
  type: string;
  tool: string | null;
  args: Record<string, unknown> | null;
  decision: string | null;
  rule: string | null;
  reason: string | null;
  model: string | null;
  latency_ms: number | null;
  fallback: boolean | null;
}

interface Turn {
  id: string;
  role: "user" | "assistant";
  text: string;
  language?: string | null;
  spoken?: string;
  meta?: Record<string, string | number | null | undefined>;
  steps?: HarnessStep[];
  blocked?: boolean;
}

const VOICE_PREF_KEY = "gnani-shop-voice";


function StepList({ steps }: { steps: HarnessStep[] }) {
  return (
    <ol className="mt-2 space-y-1.5 border-l border-night-line pl-3 text-[12px]">
      {steps
        .filter((s) => s.type !== "model_call" || s.fallback)
        .map((s, i) => {
          const tone =
            s.decision === "DENY"
              ? "text-[#ff8a8a]"
              : s.decision === "REQUIRE_CONFIRMATION"
                ? "text-[#ffce21]"
                : s.decision === "ALLOW"
                  ? "text-[#7ee2a8]"
                  : "text-on-night-soft";
          let label = s.type.replace(/_/g, " ");
          if (s.type === "tool_call_proposed") label = `AI proposed ${s.tool}`;
          if (s.type === "policy_decision")
            label = `Rulebook: ${s.decision === "REQUIRE_CONFIRMATION" ? "ASK THE HUMAN" : s.decision} · ${s.rule === "__default__" ? "no rule objected" : s.rule}`;
          if (s.type === "tool_executed") label = `Executed ${s.tool}`;
          if (s.type === "model_call") label = `Switched to backup model ${s.model}`;
          if (s.type === "malformed_tool_call") label = `Rejected malformed call to ${s.tool}`;
          if (s.type === "upsell_proposed") label = `Offer proposed: ${s.tool}`;
          if (s.type === "upsell_blocked") label = `Offer blocked: ${s.tool}`;
          return (
            <li key={i} className={tone}>
              <span className="mr-1 text-on-night-faint">{i + 1}.</span>
              {label}
              {s.type === "policy_decision" && s.args && "sku" in s.args && (
                <span className="text-on-night-faint">
                  {" "}
                  — {String(s.args.sku)}
                  {"quantity" in s.args ? ` ×${String(s.args.quantity)}` : ""}
                </span>
              )}
            </li>
          );
        })}
    </ol>
  );
}

type AnyTurn =
  | VoiceTurn
  | (Partial<VoiceTurn> & {
      reply: string;
      status: VoiceTurn["status"];
      cart: Cart;
      pending: PendingAction | null;
      payment: PaymentInfo | null;
      steps?: HarnessStep[];
    });

export default function VoiceAssistant({ onCart, onPaid: onPaidOuter }: { onCart: (cart: Cart) => void; onPaid?: () => void }) {
  const { t, lang, setLang } = useI18n();
  const [catalog, setCatalog] = useState<VoiceCatalog | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [level, setLevel] = useState(0);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [payment, setPayment] = useState<PaymentInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [typing, setTyping] = useState(false);
  const [text, setText] = useState("");
  const [speak, setSpeak] = useState(true);
  const [handsFree, setHandsFree] = useState(true);
  const [ttsModel, setTtsModel] = useState("timbre-v3.0");
  const [voice, setVoice] = useState("Shivani");
  const [openSteps, setOpenSteps] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState("");
  const [conversingUi, setConversingUi] = useState(false);

  const recorder = useRef<MicRecorder | null>(null);
  const player = useRef<PcmPlayer | null>(null);
  const vad = useRef(new VoiceActivityDetector(DEFAULT_VAD));
  const listening = useRef(false); // frames are being judged by the VAD
  const finishRef = useRef<(send: boolean) => void>(() => {});
  const conversing = useRef(false); // hands-free loop active
  const stopping = useRef(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  function setConversing(v: boolean) {
    conversing.current = v;
    setConversingUi(v);
  }

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
      conversing.current = false;
      listening.current = false;
      recorder.current?.stop();
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
    (v) =>
      ttsModel === "timbre-v3.0" ||
      !v.preferred_language ||
      v.preferred_language === lang ||
      (lang === "hi-IN" && v.preferred_language === "hi-en")
  );

  // ------------------------------------------------------------ speaking

  const say = useCallback(
    async (spokenText: string, language: string | null) => {
      if (!speak || !spokenText.trim()) return;
      setPhase("speaking");
      player.current?.stop();
      const p = new PcmPlayer();
      player.current = p;
      try {
        const v = ttsModel === "timbre-v2.5" && !voicesForModel.some((x) => x.name === voice) ? undefined : voice;
        await synthesizeStream({ text: spokenText, voice: v, model: ttsModel, language, sessionId }, (pcm, rate) =>
          p.enqueue(pcm, rate)
        );
        p.markComplete();
        // Wait until every word has actually been played — never just the
        // first gap between chunks. Safety cap: 90 s.
        await Promise.race([p.finished(), new Promise((r) => setTimeout(r, 90_000))]);
      } catch (e) {
        p.markComplete();
        setError(`Speech unavailable: ${e instanceof Error ? e.message : String(e)}`);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [speak, ttsModel, voice, sessionId, lang, catalog]
  );

  // ------------------------------------------------------------ applying a turn

  function applyTurn(r: AnyTurn, userText: string | null, language: string | null): string {
    const id = crypto.randomUUID();
    const v = r as VoiceTurn;
    const meta: Turn["meta"] = v.stt
      ? {
          "Speech model": v.stt.model ?? "prisma-v3.0",
          Detected: v.detected_language ?? "—",
          "Gnani time": v.stt.processing_time_ms != null ? `${v.stt.processing_time_ms} ms` : "—",
          "Round trip": v.stt.round_trip_ms != null ? `${v.stt.round_trip_ms} ms` : "—",
          "Voice gate": v.gate_rule === "__default__" ? "allowed" : v.gate_rule,
        }
      : undefined;
    setTurns((ts) => [
      ...ts,
      ...(userText ? [{ id: id + "-u", role: "user" as const, text: userText, language }] : []),
      {
        id,
        role: "assistant" as const,
        text: r.reply,
        spoken: v.spoken_text ?? r.reply,
        language,
        meta,
        steps: ((r as { steps?: HarnessStep[] }).steps ?? []) as HarnessStep[],
        blocked: v.gate_allowed === false && !!v.gate_rule,
      },
    ]);
    setOpenSteps(id);
    onCart(r.cart);
    setPending(r.status === "awaiting_confirmation" ? r.pending : null);
    if (r.payment && r.payment.status === "AWAITING_PAYMENT") setPayment(r.payment);
    return id;
  }

  // ------------------------------------------------------------ hands-free listening

  function stopMeter() {
    listening.current = false;
    setLevel(0);
  }

  // Called for every 20 ms of mic audio (from the audio thread, not from
  // animation frames — so it keeps working in a background tab).
  function onFrame(_pcm: Int16Array, level: number) {
    if (!listening.current || stopping.current) return;
    setLevel(level);
    const ev = vad.current.push(level);
    if (ev === "end") finishRef.current(true);
    else if (ev === "no_speech") finishRef.current(false);
  }

  async function startListening() {
    setError(null);
    setNotice(null);
    player.current?.stop();
    try {
      // One mic for the whole conversation: no re-prompt, no warm-up gap,
      // and a 400 ms pre-roll so the first syllable is never clipped.
      const rec = recorder.current ?? new MicRecorder(() => {}, (pcm, l) => onFrameRef.current(pcm, l));
      recorder.current = rec;
      await rec.start();
      vad.current.reset();
      stopping.current = false;
      listening.current = true;
      setPhase("listening");
    } catch {
      setConversing(false);
      recorder.current?.stop();
      recorder.current = null;
      setError("Microphone permission is needed for voice. You can type instead.");
      setTyping(true);
      setPhase("idle");
    }
  }

  async function finishListening(send: boolean) {
    if (stopping.current) return;
    stopping.current = true;
    stopMeter();
    const rec = recorder.current;
    if (!rec) return;
    const secs = rec.seconds();
    const wav = rec.take(); // mic stays open for the next turn
    if (!send || secs < 0.4) {
      releaseMic();
      setConversing(false);
      setPhase("idle");
      setNotice(send ? null : "I didn't hear anything — tap the mic and speak.");
      return;
    }
    setPhase("thinking");
    try {
      const r = await sendVoiceTurn(sessionId, wav, { ttsModel, languageHint: lang === "en-IN" ? null : lang });
      if (r.fell_back_to_text) {
        releaseMic();
        setConversing(false);
        setTyping(true);
        applyTurn(r, null, r.language);
        setPhase("idle");
        return;
      }
      if (r.language && r.language !== lang) setLang(r.language);
      applyTurn(r, r.transcript || "…", r.language);
      await say(r.spoken_text, r.language);
      const needsTap = r.status === "awaiting_confirmation" || (r.payment && r.payment.status === "AWAITING_PAYMENT");
      if (conversing.current && handsFree && !needsTap) {
        await startListening();
      } else {
        releaseMic();
        setConversing(false);
        setPhase("idle");
      }
    } catch (e) {
      releaseMic();
      setConversing(false);
      setError(e instanceof Error ? e.message : String(e));
      setPhase("idle");
    }
  }

  function releaseMic() {
    stopMeter();
    recorder.current?.stop();
    recorder.current = null;
  }

  function endConversation() {
    setConversing(false);
    player.current?.stop();
    stopping.current = true;
    releaseMic();
    setPhase("idle");
  }

  // Callbacks living on the long-lived mic must always see the latest state.
  const onFrameRef = useRef<(pcm: Int16Array, level: number) => void>(() => {});
  useEffect(() => {
    onFrameRef.current = onFrame;
    finishRef.current = finishListening;
  });

  function onMic() {
    unlockAudio(); // inside the click, so the reply is allowed to play
    if (phase === "listening") return void finishListening(true); // manual stop → send now
    if (phase === "speaking") return endConversation();
    if (phase === "idle") {
      setConversing(true);
      startListening();
    }
  }

  // ------------------------------------------------------------ typed + taps

  async function sendText() {
    const msg = text.trim();
    if (!msg) return;
    setText("");
    unlockAudio();
    setPhase("thinking");
    setError(null);
    try {
      const r = await sendAgentMessage(sessionId, msg, null, lang);
      applyTurn(r as AnyTurn, msg, lang);
      await say(r.reply, lang);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPhase("idle");
    }
  }

  async function decide(approve: boolean) {
    setPhase("thinking");
    try {
      const r = await confirmPendingAction(sessionId, approve);
      applyTurn(r as AnyTurn, null, lang);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPhase("idle");
    }
  }

  function onPaid(r: PaymentResult) {
    setTurns((ts) => [
      ...ts,
      {
        id: crypto.randomUUID(),
        role: "assistant",
        text: r.status === "PAID" ? `${t("orderPlaced")} · #${r.order_id}` : `${t("codPlaced")} · #${r.order_id}`,
        language: lang,
      },
    ]);
    setPending(null);
    onPaidOuter?.();
  }

  function newChat() {
    endConversation();
    setSessionId(startNewSessionId());
    setTurns([]);
    setPending(null);
  }

  // ------------------------------------------------------------ render

  const stateLabel =
    phase === "listening" ? t("listening") : phase === "thinking" ? t("thinking") : phase === "speaking" ? t("speaking") : t("tapToSpeak");
  const bars = Array.from({ length: 24 });

  return (
    <section className="band-night-fade">
      <div className="mx-auto grid max-w-[1280px] gap-10 px-4 py-12 sm:px-6 lg:grid-cols-[minmax(0,460px)_1fr] lg:py-16">
        {/* Left: headline + mic */}
        <div className="flex flex-col gap-8">
          <div>
            <span className="inline-flex items-center rounded-full bg-accent px-2.5 py-1 text-[12px] font-medium text-white">
              Powered by Gnani Vachana
            </span>
            <h1 className="display mt-5 text-[34px] text-white sm:text-[44px]">{t("heroTitle")}</h1>
            <p className="mt-3 max-w-md text-[17px] leading-relaxed text-on-night-soft">{t("heroSub")}</p>
          </div>

          <div className="flex items-center gap-6">
            <button
              onClick={onMic}
              disabled={phase === "thinking"}
              aria-label={stateLabel}
              className={`relative flex h-28 w-28 shrink-0 items-center justify-center rounded-full bg-accent text-white transition-transform duration-150 active:scale-95 disabled:opacity-70 ${
                phase === "listening" ? "voice-pulse" : ""
              }`}
            >
              <span
                className="absolute inset-0 rounded-full bg-accent/30"
                style={{ transform: `scale(${1 + level * 0.7})` }}
                aria-hidden
              />
              {phase === "thinking" ? (
                <Loader2 size={40} className="relative animate-spin" />
              ) : phase === "speaking" ? (
                <Volume2 size={40} className="relative" />
              ) : phase === "listening" ? (
                <Square size={30} className="relative" fill="currentColor" />
              ) : (
                <Mic size={44} className="relative" />
              )}
            </button>
            <div className="min-w-0">
              <p className="display text-[22px] text-white">
                {stateLabel}
                {phase === "thinking" && (
                  <span className="ml-1">
                    <span className="voice-dot">.</span>
                    <span className="voice-dot [animation-delay:150ms]">.</span>
                    <span className="voice-dot [animation-delay:300ms]">.</span>
                  </span>
                )}
              </p>
              <div className="mt-2 flex h-6 items-center gap-[3px]" aria-hidden>
                {bars.map((_, i) => (
                  <span
                    key={i}
                    className={`w-[3px] rounded-full ${phase === "speaking" ? "speak-bar bg-link-night" : "bg-accent"}`}
                    style={{
                      height:
                        phase === "listening"
                          ? `${Math.max(3, Math.min(24, level * 60 * (0.4 + Math.abs(Math.sin(i * 1.7)))))}px`
                          : phase === "speaking"
                            ? "22px"
                            : "3px",
                      animationDelay: `${(i % 6) * 90}ms`,
                    }}
                  />
                ))}
              </div>
              <p className="mt-2 text-[13px] text-on-night-faint">
                {phase === "listening"
                  ? "Stops by itself when you pause · click to send now"
                  : handsFree
                    ? "Hands-free: it listens again after each answer"
                    : "One question at a time"}
              </p>
            </div>
          </div>

          <div>
            <p className="mb-2 text-[12px] font-medium uppercase tracking-[0.6px] text-on-night-faint">
              I&apos;m speaking — a hint for Gnani, which still auto-detects
            </p>
            <div className="flex flex-wrap gap-2">
              {LANGUAGES.map((l) => (
                <button
                  key={l.code}
                  onClick={() => setLang(l.code)}
                  title={l.english}
                  className={`rounded-full px-3.5 py-1.5 text-[13px] font-bold transition-colors ${
                    lang === l.code ? "bg-white text-ink" : "bg-white/10 text-white hover:bg-white/20"
                  }`}
                >
                  {l.native}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Right: the conversation */}
        <div className="flex min-h-[520px] flex-col overflow-hidden rounded-md bg-night-card">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-night-line px-4 py-3">
            <div className="flex flex-wrap items-center gap-2 text-xs text-on-night-faint">
              <select
                value={ttsModel}
                onChange={(e) => {
                  setTtsModel(e.target.value);
                  if (e.target.value === "timbre-v3.0") setVoice("Shivani");
                }}
                className="h-8 rounded-full border border-night-line bg-night px-3 text-xs text-white"
              >
                <option value="timbre-v3.0">Timbre v3.0 · 13 voices</option>
                <option value="timbre-v2.5">Timbre v2.5 · native voices</option>
              </select>
              <select
                value={voice}
                onChange={(e) => setVoice(e.target.value)}
                className="h-8 rounded-full border border-night-line bg-night px-3 text-xs text-white"
              >
                {voicesForModel.map((v) => (
                  <option key={v.name} value={v.name}>
                    {v.name} {v.gender ? `· ${v.gender}` : ""}
                  </option>
                ))}
              </select>
              <label className="flex cursor-pointer items-center gap-1.5 rounded-full border border-night-line px-3 py-1.5 text-white">
                <input type="checkbox" checked={handsFree} onChange={(e) => setHandsFree(e.target.checked)} className="accent-[#0070d1]" />
                Hands-free
              </label>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setSpeak((s) => !s)}
                className="rounded-full p-2 text-on-night-soft hover:text-white"
                title={speak ? "Mute replies" : "Speak replies"}
              >
                {speak ? <Volume2 size={16} /> : <VolumeX size={16} />}
              </button>
              {(phase !== "idle" || conversingUi) && (
                <Button size="sm" variant="night" onClick={endConversation}>
                  End
                </Button>
              )}
              <Button size="sm" variant="night" onClick={newChat}>
                {t("newChat")}
              </Button>
            </div>
          </div>

          <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-5 py-5" style={{ maxHeight: 460 }}>
            {turns.length === 0 && (
              <div className="mx-auto mt-4 max-w-sm space-y-2 text-center">
                <p className="display text-[22px] text-white">Try saying</p>
                {[
                  "నాకు రెండు ఆట్టా ప్యాకెట్లు మరియు పాలు కావాలి",
                  "do kilo atta aur ek litre doodh",
                  "ஒரு டப்பா நெய் சேர்",
                  "Add Maggi and a cold drink under ₹200",
                ].map((s) => (
                  <p key={s} className="rounded-full bg-white/[0.06] px-4 py-2 text-[14px] text-on-night-soft">
                    “{s}”
                  </p>
                ))}
              </div>
            )}
            {turns.map((turn) => (
              <div key={turn.id} className={`flex flex-col ${turn.role === "user" ? "items-end" : "items-start"}`}>
                <div
                  className={`max-w-[88%] whitespace-pre-wrap rounded-md px-4 py-2.5 text-[15px] leading-relaxed ${
                    turn.role === "user"
                      ? "bg-accent text-white"
                      : turn.blocked
                        ? "bg-[#3a2a08] text-[#ffce21]"
                        : "bg-white/[0.07] text-white"
                  }`}
                >
                  {turn.text}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2 px-0.5 text-[11px] text-on-night-faint">
                  {turn.role === "user" ? t("youSaid") : "Gnani Shop"}
                  {turn.language && <span className="rounded-full bg-white/10 px-2 py-0.5 text-white">{nativeName(turn.language)}</span>}
                  {turn.role === "assistant" && turn.spoken && (
                    <button
                      className="hover:text-white"
                      onClick={() => {
                        unlockAudio();
                        say(turn.spoken!, turn.language ?? null).then(() => setPhase("idle"));
                      }}
                      title="Play again"
                    >
                      <Volume2 size={12} />
                    </button>
                  )}
                  {(turn.steps?.length || turn.meta) && (
                    <button
                      className="inline-flex items-center gap-0.5 hover:text-white"
                      onClick={() => setOpenSteps(openSteps === turn.id ? null : turn.id)}
                    >
                      Harness loop
                      {turn.steps?.length ? ` · ${turn.steps.filter((s) => s.type !== "model_call").length} steps` : ""}
                      <ChevronDown size={11} className={openSteps === turn.id ? "rotate-180" : ""} />
                    </button>
                  )}
                </div>
                {openSteps === turn.id && (turn.steps?.length || turn.meta) && (
                  <div className="mt-1 w-full max-w-[88%] rounded-md bg-night px-3 py-2.5">
                    {turn.meta && (
                      <dl className="grid grid-cols-2 gap-x-4 gap-y-0.5 font-mono text-[11px] sm:grid-cols-3">
                        {Object.entries(turn.meta).map(([k, v]) => (
                          <div key={k}>
                            <dt className="inline text-on-night-faint">{k}: </dt>
                            <dd className="inline text-white">{String(v ?? "—")}</dd>
                          </div>
                        ))}
                      </dl>
                    )}
                    {turn.steps && turn.steps.length > 0 && <StepList steps={turn.steps} />}
                  </div>
                )}
              </div>
            ))}
          </div>

          {pending && (
            <div className="mx-4 mb-3 rounded-md bg-[#3a2a08] p-4">
              <p className="flex items-center gap-1.5 text-[15px] font-semibold text-[#ffce21]">
                <ShieldCheck size={16} /> {t("needsTap")}
              </p>
              <p className="mt-1 text-[13px] text-on-night-soft">
                {pending.reason} <span className="font-mono text-on-night-faint">({pending.rule_name})</span>
              </p>
              <div className="mt-3 flex gap-2">
                <Button size="sm" variant="commerce" onClick={() => decide(true)}>
                  {t("confirm")}
                </Button>
                <Button size="sm" variant="night" onClick={() => decide(false)}>
                  {t("decline")}
                </Button>
              </div>
            </div>
          )}

          {notice && <p className="mx-4 mb-3 rounded-md bg-white/[0.06] px-3 py-2 text-xs text-on-night-soft">{notice}</p>}
          {error && <p className="mx-4 mb-3 rounded-md bg-[#3a0d16] px-3 py-2 text-xs text-[#ff8a8a]">{error}</p>}

          <div className="border-t border-night-line p-3">
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
                  className="h-11 flex-1 rounded-full border border-night-line bg-night px-4 text-sm text-white outline-none placeholder:text-on-night-faint focus:border-accent"
                />
                <Button type="submit" variant="primary" disabled={phase === "thinking" || !text.trim()}>
                  <Send size={14} /> {t("send")}
                </Button>
              </form>
            ) : (
              <button onClick={() => setTyping(true)} className="inline-flex items-center gap-1.5 px-1 text-xs text-on-night-faint hover:text-white">
                <Keyboard size={14} /> {t("typeInstead")}
              </button>
            )}
          </div>
        </div>
      </div>

      {payment && <PaymentSheet payment={payment} onClose={() => setPayment(null)} onDone={onPaid} />}
    </section>
  );
}
