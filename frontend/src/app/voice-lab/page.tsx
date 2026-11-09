"use client";

// Voice Lab — every Gnani Vachana capability this app uses, side by side,
// with Gnani's own timings. Speech-to-text (Prisma v3.0) in all four output
// formats and with/without catalog keyterms; text-to-speech (Timbre v3.0 /
// v2.5) streamed vs. whole-clip, with audio tags; and the full voice gallery.

import { useEffect, useRef, useState } from "react";
import { FlaskConical, Loader2, Mic, Play, Square, Upload, Zap } from "lucide-react";
import RequireAuth from "@/components/RequireAuth";
import Button from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { fetchVoiceCatalog, labTranscribe, synthesize, synthesizeStream } from "@/lib/api";
import { LANGUAGES, nativeName, useI18n } from "@/lib/i18n";
import { MicRecorder, PcmPlayer, playBlob } from "@/lib/voice";
import type { LabResult, VoiceCatalog } from "@/lib/types";

const SAMPLES: Record<string, string> = {
  "en-IN": "Welcome to Gnani Shop. Two kilos of atta and one litre of milk will be ₹347.",
  "hi-IN": "Gnani Shop में आपका स्वागत है। दो किलो आटा और एक लीटर दूध, कुल ₹347।",
  "ta-IN": "Gnani Shop-க்கு வரவேற்கிறோம். இரண்டு கிலோ மாவு மற்றும் ஒரு லிட்டர் பால், மொத்தம் ₹347.",
  "te-IN": "Gnani Shop కు స్వాగతం. రెండు కిలోల పిండి మరియు ఒక లీటర్ పాలు, మొత్తం ₹347.",
  "kn-IN": "Gnani Shop ಗೆ ಸ್ವಾಗತ. ಎರಡು ಕಿಲೋ ಹಿಟ್ಟು ಮತ್ತು ಒಂದು ಲೀಟರ್ ಹಾಲು, ಒಟ್ಟು ₹347.",
  "ml-IN": "Gnani Shop-ലേക്ക് സ്വാഗതം. രണ്ട് കിലോ ആട്ടയും ഒരു ലിറ്റർ പാലും, ആകെ ₹347.",
  "mr-IN": "Gnani Shop मध्ये आपले स्वागत आहे. दोन किलो पीठ आणि एक लीटर दूध, एकूण ₹347.",
  "bn-IN": "Gnani Shop-এ স্বাগতম। দুই কেজি আটা আর এক লিটার দুধ, মোট ₹347।",
  "gu-IN": "Gnani Shop માં આપનું સ્વાગત છે. બે કિલો લોટ અને એક લીટર દૂધ, કુલ ₹347.",
  "pa-IN": "Gnani Shop ਵਿੱਚ ਤੁਹਾਡਾ ਸੁਆਗਤ ਹੈ। ਦੋ ਕਿਲੋ ਆਟਾ ਅਤੇ ਇੱਕ ਲੀਟਰ ਦੁੱਧ, ਕੁੱਲ ₹347।",
};

const FORMAT_HELP: Record<string, string> = {
  transcribe: "Digits & symbols, English words in Latin — what the shop uses (\"2 किलो\")",
  verbatim: "Everything in the spoken language's own script, numbers as words",
  codemix: "Native script, English words kept in Latin, numbers as words",
  transliterate: "The whole transcript in Latin letters",
};

export default function VoiceLabPage() {
  return (
    <RequireAuth>
      <VoiceLab />
    </RequireAuth>
  );
}

function VoiceLab() {
  const [catalog, setCatalog] = useState<VoiceCatalog | null>(null);
  useEffect(() => {
    fetchVoiceCatalog().then(setCatalog).catch(() => {});
  }, []);

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-8 sm:px-6">
      <header>
        <Badge variant="voice">
          <FlaskConical size={12} className="mr-1" /> Gnani Vachana
        </Badge>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-ink">Voice Lab</h1>
        <p className="mt-1 max-w-3xl text-sm text-ink-soft">
          See exactly what Gnani&apos;s models do. Prisma v3.0 hears 10 Indian languages and detects which one was spoken; Timbre
          speaks them back in 55 voices. Every number on this page is Gnani&apos;s own measured timing.
        </p>
      </header>
      <SpeechToText />
      <TextToSpeech catalog={catalog} />
      <VoiceGallery catalog={catalog} />
    </div>
  );
}

// ------------------------------------------------------------------ STT

function SpeechToText() {
  const [recording, setRecording] = useState(false);
  const [level, setLevel] = useState(0);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<LabResult[] | null>(null);
  const [keytermCount, setKeytermCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const rec = useRef<MicRecorder | null>(null);

  async function run(wav: Blob) {
    setBusy(true);
    setError(null);
    try {
      const r = await labTranscribe(wav, ["transcribe", "verbatim", "codemix", "transliterate"], true);
      setResults(r.results);
      setKeytermCount(r.keyterm_count);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function toggle() {
    if (recording) {
      const wav = await rec.current!.stop();
      rec.current = null;
      setRecording(false);
      await run(wav);
    } else {
      try {
        const r = new MicRecorder(setLevel);
        await r.start();
        rec.current = r;
        setRecording(true);
      } catch {
        setError("Microphone permission is needed — or upload a WAV file instead.");
      }
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>1 · Speech to text — Prisma v3.0</CardTitle>
        <CardDescription>
          Say something like “2 किलो Aashirvaad आटा और एक Amul दूध” in any language (30 s max). The same clip runs through all four
          output formats with <span className="font-mono">language_code=indic-auto</span>, plus once without the {keytermCount || "catalog"}{" "}
          keyterms, so you can see what each one changes.
        </CardDescription>
      </CardHeader>
      <CardBody className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={toggle}
            disabled={busy}
            className={`relative flex h-14 w-14 items-center justify-center rounded-full text-white ${recording ? "bg-voice voice-pulse" : "bg-voice hover:bg-voice-deep"} disabled:opacity-60`}
          >
            <span className="absolute inset-0 rounded-full bg-voice/30" style={{ transform: `scale(${1 + level * 0.5})` }} />
            {busy ? <Loader2 className="relative animate-spin" /> : recording ? <Square className="relative" size={20} fill="currentColor" /> : <Mic className="relative" />}
          </button>
          <span className="text-sm text-ink-soft">{recording ? "Recording… tap to stop" : busy ? "Running 5 transcriptions…" : "Tap to record"}</span>
          <label className="ml-auto inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-line px-3 py-1.5 text-xs text-ink-soft hover:border-line-strong">
            <Upload size={14} /> Upload WAV
            <input type="file" accept="audio/wav,audio/*" className="hidden" onChange={(e) => e.target.files?.[0] && run(e.target.files[0])} />
          </label>
        </div>
        {error && <p className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{error}</p>}
        {results && (
          <div className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full text-sm">
              <thead className="bg-black/[0.02] text-left text-xs text-ink-faint">
                <tr>
                  <th className="px-3 py-2">Format</th>
                  <th className="px-3 py-2">Keyterms</th>
                  <th className="px-3 py-2">Transcript</th>
                  <th className="px-3 py-2">Language</th>
                  <th className="px-3 py-2 text-right">Gnani ms</th>
                  <th className="px-3 py-2 text-right">Round trip</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r, i) => (
                  <tr key={i} className="border-t border-line align-top">
                    <td className="px-3 py-2">
                      <span className="font-mono text-xs">{r.format}</span>
                      <p className="mt-0.5 max-w-[14rem] text-[11px] text-ink-faint">{FORMAT_HELP[r.format]}</p>
                    </td>
                    <td className="px-3 py-2">{r.keyterms ? <Badge variant="success">on</Badge> : <Badge>off</Badge>}</td>
                    <td className="px-3 py-2 text-ink">{r.error ? <span className="text-danger">{r.error}</span> : r.transcript || <span className="text-ink-faint">(no speech)</span>}</td>
                    <td className="px-3 py-2">{r.detected_language ? <Badge variant="voice">{nativeName(r.detected_language)}</Badge> : "—"}</td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums">{r.processing_time_ms ?? "—"}</td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums">{r.round_trip_ms ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

// ------------------------------------------------------------------ TTS

function TextToSpeech({ catalog }: { catalog: VoiceCatalog | null }) {
  const { lang } = useI18n();
  const [language, setLanguage] = useState<string>(lang);
  const [text, setText] = useState(SAMPLES[lang] ?? SAMPLES["en-IN"]);
  const [model, setModel] = useState("timbre-v3.0");
  const [voice, setVoice] = useState("Shivani");
  const [speed, setSpeed] = useState(1);
  const [busy, setBusy] = useState<"stream" | "sync" | null>(null);
  const [timing, setTiming] = useState<{ stream?: number | null; sync?: number | null }>({});
  const [error, setError] = useState<string | null>(null);
  const player = useRef<PcmPlayer | null>(null);

  const voices = catalog?.tts[model]?.voices ?? [];
  const tags = catalog?.tts[model]?.audio_tags ?? [];

  function pickLanguage(code: string) {
    setLanguage(code);
    setText(SAMPLES[code] ?? text);
    if (model === "timbre-v2.5") {
      const v = (catalog?.tts["timbre-v2.5"]?.voices ?? []).find((x) => x.preferred_language === code);
      if (v) setVoice(v.name);
    }
  }

  async function streamIt() {
    setBusy("stream");
    setError(null);
    player.current?.stop();
    const p = new PcmPlayer();
    player.current = p;
    try {
      const { firstChunkMs } = await synthesizeStream({ text, voice, model, language, speed }, (pcm, rate) => p.enqueue(pcm, rate));
      setTiming((t) => ({ ...t, stream: firstChunkMs }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function syncIt() {
    setBusy("sync");
    setError(null);
    const started = performance.now();
    try {
      const { audio } = await synthesize({ text, voice, model, language, speed });
      setTiming((t) => ({ ...t, sync: Math.round(performance.now() - started) }));
      await playBlob(audio);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>2 · Text to speech — Timbre</CardTitle>
        <CardDescription>
          Streaming (SSE) starts playing as soon as the first chunk arrives; the sync call waits for the whole clip. Rupee amounts,
          lakh-style numbers and dates are read correctly in every language. Audio tags work on Timbre v3.0.
        </CardDescription>
      </CardHeader>
      <CardBody className="space-y-3">
        <div className="flex flex-wrap gap-1.5">
          {LANGUAGES.map((l) => (
            <button
              key={l.code}
              onClick={() => pickLanguage(l.code)}
              className={`rounded-full border px-2.5 py-1 text-xs ${language === l.code ? "border-voice bg-voice-soft font-semibold text-voice-deep" : "border-line text-ink-soft"}`}
            >
              {l.native}
            </button>
          ))}
        </div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          className="w-full rounded-md border border-line bg-surface p-3 text-sm outline-none focus:border-accent"
        />
        {tags.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <span className="text-ink-faint">Audio tags:</span>
            {tags.map((tag) => (
              <button key={tag} onClick={() => setText((t) => `<${tag}> ${t}`)} className="rounded border border-line px-1.5 py-0.5 font-mono text-[11px] text-ink-soft hover:border-voice hover:text-voice-deep">
                &lt;{tag}&gt;
              </button>
            ))}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <select value={model} onChange={(e) => { setModel(e.target.value); setVoice(e.target.value === "timbre-v3.0" ? "Shivani" : "Nalini"); }} className="rounded-md border border-line bg-surface px-2 py-1.5">
            <option value="timbre-v3.0">Timbre v3.0</option>
            <option value="timbre-v2.5">Timbre v2.5</option>
          </select>
          <select value={voice} onChange={(e) => setVoice(e.target.value)} className="rounded-md border border-line bg-surface px-2 py-1.5">
            {voices.map((v) => (
              <option key={v.name} value={v.name}>
                {v.name} ({v.gender}){v.preferred_language ? ` · ${nativeName(v.preferred_language) || "Hinglish"}` : ""}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-1.5 text-ink-soft">
            Speed
            <input type="range" min={0.85} max={1.15} step={0.05} value={speed} onChange={(e) => setSpeed(Number(e.target.value))} />
            <span className="font-mono">{speed.toFixed(2)}</span>
          </label>
          <div className="ml-auto flex gap-2">
            <Button variant="primary" size="sm" onClick={streamIt} disabled={busy !== null || !text.trim()}>
              {busy === "stream" ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />} Stream
            </Button>
            <Button size="sm" onClick={syncIt} disabled={busy !== null || !text.trim()}>
              {busy === "sync" ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />} Whole clip
            </Button>
          </div>
        </div>
        {(timing.stream != null || timing.sync != null) && (
          <div className="grid grid-cols-2 gap-3 sm:max-w-md">
            <div className="rounded-md border border-line p-3">
              <p className="text-[11px] uppercase tracking-wide text-ink-faint">Streaming · first audio</p>
              <p className="font-mono text-xl font-semibold tabular-nums text-success">{timing.stream != null ? `${timing.stream} ms` : "—"}</p>
            </div>
            <div className="rounded-md border border-line p-3">
              <p className="text-[11px] uppercase tracking-wide text-ink-faint">Whole clip · ready</p>
              <p className="font-mono text-xl font-semibold tabular-nums text-ink">{timing.sync != null ? `${timing.sync} ms` : "—"}</p>
            </div>
          </div>
        )}
        {error && <p className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{error}</p>}
      </CardBody>
    </Card>
  );
}

// ------------------------------------------------------------------ gallery

function VoiceGallery({ catalog }: { catalog: VoiceCatalog | null }) {
  const { lang } = useI18n();
  const [language, setLanguage] = useState<string>(lang);
  const [playing, setPlaying] = useState<string | null>(null);
  const voices = catalog?.tts["timbre-v3.0"]?.voices ?? [];

  async function hear(name: string) {
    setPlaying(name);
    const p = new PcmPlayer();
    try {
      await synthesizeStream({ text: SAMPLES[language], voice: name, model: "timbre-v3.0", language }, (pcm, rate) => p.enqueue(pcm, rate));
    } finally {
      setTimeout(() => setPlaying(null), 1500);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>3 · Voice gallery — 13 voices, each speaks all 10 languages</CardTitle>
        <CardDescription>Timbre v3.0 lets one persona follow the buyer from Hindi to Tamil mid-conversation. Pick a language, then any voice.</CardDescription>
      </CardHeader>
      <CardBody className="space-y-3">
        <select value={language} onChange={(e) => setLanguage(e.target.value)} className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm">
          {LANGUAGES.map((l) => (
            <option key={l.code} value={l.code}>
              {l.native} · {l.english}
            </option>
          ))}
        </select>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
          {voices.map((v) => (
            <button
              key={v.name}
              onClick={() => hear(v.name)}
              className={`flex flex-col items-start rounded-lg border p-3 text-left transition ${playing === v.name ? "border-voice bg-voice-soft" : "border-line hover:border-line-strong"}`}
            >
              <span className="text-sm font-medium text-ink">{v.name}</span>
              <span className="text-[11px] text-ink-faint">{v.gender}</span>
              <span className="mt-2 inline-flex items-center gap-1 text-[11px] text-voice-deep">
                {playing === v.name ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} />} {nativeName(language)}
              </span>
            </button>
          ))}
        </div>
      </CardBody>
    </Card>
  );
}
