"use client";

// Merchant voice features, all on Gnani Vachana:
//   Voice Insights — how buyers use voice (languages, Gnani timings, gate refusals, fallbacks)
//   Shop Voice     — clone the merchant's own voice (vachana-vc-v1), with explicit consent
//   Call Insights  — batch-transcribe phone-order recordings with speaker separation,
//                    feeding the same anonymous demand alerts as chat

import { useCallback, useEffect, useRef, useState } from "react";
import { AudioLines, Loader2, Mic, Phone, Play, RefreshCw, Square, Trash2, Upload } from "lucide-react";
import RequireAuth from "@/components/RequireAuth";
import Button from "@/components/ui/Button";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Card, CardBody, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import MetricCard from "@/components/ui/MetricCard";
import {
  createVoiceProfile,
  deleteVoiceProfile,
  fetchCallBatches,
  fetchVoiceInsights,
  fetchVoiceProfile,
  previewVoiceProfile,
  refreshCallBatch,
  uploadCalls,
} from "@/lib/api";
import { nativeName } from "@/lib/i18n";
import { MicRecorder, playBlob } from "@/lib/voice";
import type { CallBatch, VoiceInsights, VoiceProfileInfo } from "@/lib/types";

export default function MerchantVoicePage() {
  return (
    <RequireAuth allow={["merchant"]}>
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-8 sm:px-6">
        <header>
          <Badge variant="voice">
            <AudioLines size={12} className="mr-1" /> Gnani Vachana
          </Badge>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-ink">Voice</h1>
          <p className="mt-1 text-sm text-ink-soft">How your customers talk to the shop, your shop&apos;s own voice, and what phone orders are asking for.</p>
        </header>
        <InsightsSection />
        <ShopVoiceSection />
        <CallInsightsSection />
      </div>
    </RequireAuth>
  );
}

function InsightsSection() {
  const [data, setData] = useState<VoiceInsights | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    fetchVoiceInsights().then(setData).catch((e) => setError(e.message));
  }, []);
  const maxTurns = Math.max(1, ...(data?.languages.map((l) => l.turns) ?? [1]));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Voice Insights</CardTitle>
        <CardDescription>Computed from the audit log — every voice turn is recorded with Gnani&apos;s detected language and timings. Audio itself is never stored.</CardDescription>
      </CardHeader>
      <CardBody className="space-y-5">
        {error && <p className="text-sm text-danger">{error}</p>}
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label="Voice turns" value={String(data?.voice_turns ?? "—")} />
          <MetricCard
            label="Speech-to-text p50"
            value={data?.stt_round_trip_ms.p50 != null ? `${data.stt_round_trip_ms.p50} ms` : "—"}
            meta={data?.stt_model_processing_ms.p50 != null ? `Gnani model: ${data.stt_model_processing_ms.p50} ms` : undefined}
          />
          <MetricCard label="Fell back to text" value={data ? `${Math.round(data.fallback_rate * 100)}%` : "—"} meta={data ? `${data.fallback_to_text} turn(s)` : undefined} tone={data && data.fallback_rate > 0.1 ? "danger" : "default"} />
          <MetricCard label="Audio heard" value={data ? `${data.audio_seconds_transcribed}s` : "—"} meta={data ? `${data.characters_spoken} characters spoken` : undefined} />
        </div>
        <div className="grid gap-5 md:grid-cols-2">
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-faint">Languages customers spoke</p>
            {data?.languages.length ? (
              <ul className="space-y-1.5">
                {data.languages.map((l) => (
                  <li key={l.code} className="flex items-center gap-2 text-sm">
                    <span className="w-24 shrink-0 text-ink">{l.native_name}</span>
                    <span className="h-2.5 rounded-full bg-voice" style={{ width: `${(l.turns / maxTurns) * 100}%`, minWidth: 6 }} />
                    <span className="font-mono text-xs tabular-nums text-ink-soft">{l.turns}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-ink-faint">No voice turns yet.</p>
            )}
          </div>
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-faint">Voice gate refusals (never acted on)</p>
            {data?.gate_refusals.length ? (
              <ul className="space-y-1 text-sm">
                {data.gate_refusals.map((g) => (
                  <li key={g.rule} className="flex justify-between">
                    <span className="font-mono text-xs text-ink">{g.rule}</span>
                    <span className="font-mono text-xs tabular-nums">{g.count}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-ink-faint">None.</p>
            )}
            <p className="mb-2 mt-4 text-xs font-medium uppercase tracking-wide text-ink-faint">Voices used for replies</p>
            <div className="flex flex-wrap gap-1.5">
              {(data?.voices_used ?? []).map((v) => (
                <Badge key={v.voice} variant="accent">
                  {v.voice} · {v.replies}
                </Badge>
              ))}
            </div>
          </div>
        </div>
      </CardBody>
    </Card>
  );
}

function ShopVoiceSection() {
  const [info, setInfo] = useState<VoiceProfileInfo | null>(null);
  const [name, setName] = useState("My shop voice");
  const [consent, setConsent] = useState(false);
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [wav, setWav] = useState<Blob | null>(null);
  const [busy, setBusy] = useState(false);
  const [previewText, setPreviewText] = useState("नमस्ते! आज ताज़ा सब्ज़ियों पर 10% की छूट है।");
  const [error, setError] = useState<string | null>(null);
  const rec = useRef<MicRecorder | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    fetchVoiceProfile().then(setInfo).catch((e) => setError(e.message));
  }, []);

  async function toggle() {
    if (recording) {
      if (timer.current) clearInterval(timer.current);
      setWav(await rec.current!.stop());
      rec.current = null;
      setRecording(false);
    } else {
      const r = new MicRecorder();
      await r.start();
      rec.current = r;
      setRecording(true);
      setSeconds(0);
      setWav(null);
      timer.current = setInterval(() => setSeconds((s) => s + 1), 1000);
    }
  }

  async function create() {
    if (!wav) return;
    setBusy(true);
    setError(null);
    try {
      setInfo(await createVoiceProfile(wav, name, consent));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function preview() {
    setBusy(true);
    try {
      await playBlob(await previewVoiceProfile(previewText));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Shop Voice — voice cloning</CardTitle>
        <CardDescription>
          Record 5–30 seconds of your own voice. Gnani&apos;s <span className="font-mono">vachana-vc-v1</span> turns it into a voice that can speak your
          offers in any language. Only your own voice, only with your consent — the recording itself is never stored.
        </CardDescription>
      </CardHeader>
      <CardBody className="space-y-4">
        {info?.profile ? (
          <div className="space-y-3">
            <p className="text-sm text-ink">
              <span className="font-medium">{info.profile.display_name}</span> · created {new Date(info.profile.created_at).toLocaleDateString()} from{" "}
              {info.profile.reference_seconds ?? "?"}s of audio
            </p>
            <div className="flex flex-wrap gap-2">
              <input value={previewText} onChange={(e) => setPreviewText(e.target.value)} className="min-w-64 flex-1 rounded-md border border-line px-3 py-2 text-sm" />
              <Button variant="primary" onClick={preview} disabled={busy}>
                {busy ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />} Speak in my voice
              </Button>
              <Button
                variant="destructive"
                onClick={async () => {
                  await deleteVoiceProfile();
                  setInfo(await fetchVoiceProfile());
                }}
              >
                <Trash2 size={14} /> Delete
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <button onClick={toggle} className={`flex h-12 w-12 items-center justify-center rounded-full text-white ${recording ? "bg-voice voice-pulse" : "bg-voice"}`}>
                {recording ? <Square size={18} fill="currentColor" /> : <Mic size={20} />}
              </button>
              <span className="font-mono text-sm tabular-nums text-ink-soft">{recording ? `${seconds}s — read anything aloud, 5 to 30 seconds` : wav ? "Recording ready" : "Tap to record"}</span>
              <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-line px-3 py-1.5 text-xs text-ink-soft">
                <Upload size={14} /> or upload WAV
                <input type="file" accept="audio/wav" className="hidden" onChange={(e) => e.target.files?.[0] && setWav(e.target.files[0])} />
              </label>
            </div>
            <input value={name} onChange={(e) => setName(e.target.value)} className="w-full max-w-sm rounded-md border border-line px-3 py-2 text-sm" />
            <label className="flex items-start gap-2 text-sm text-ink">
              <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-1" />
              <span>{info?.consent_text}</span>
            </label>
            <Button variant="primary" onClick={create} disabled={!wav || !consent || busy}>
              {busy ? <Loader2 size={14} className="animate-spin" /> : null} Create shop voice
            </Button>
          </div>
        )}
        {error && <p className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{error}</p>}
      </CardBody>
    </Card>
  );
}

function CallInsightsSection() {
  const [batches, setBatches] = useState<CallBatch[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchCallBatches().then(setBatches).catch((e) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    setError(null);
    try {
      await uploadCalls(Array.from(files));
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function refresh(id: number) {
    try {
      const b = await refreshCallBatch(id);
      setBatches((bs) => bs.map((x) => (x.id === id ? b : x)));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Call Insights — batch transcription</CardTitle>
        <CardDescription>
          Upload recordings of phone orders (up to 10). Gnani transcribes them in the background with speaker separation; anything customers ask for
          becomes an anonymous demand signal, counted together with what they say in the app.
        </CardDescription>
      </CardHeader>
      <CardBody className="space-y-4">
        <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-dashed border-line-strong px-4 py-3 text-sm text-ink-soft hover:border-voice">
          {busy ? <Loader2 size={16} className="animate-spin" /> : <Phone size={16} />} Upload call recordings (WAV / MP3)
          <input type="file" multiple accept="audio/*" className="hidden" onChange={(e) => upload(e.target.files)} />
        </label>
        {error && <p className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{error}</p>}
        {batches.map((b) => (
          <div key={b.id} className="rounded-lg border border-line p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-medium text-ink">
                Batch #{b.id} · {b.files.length} file(s) <StatusBadge status={b.status} className="ml-2" />
              </p>
              <div className="flex items-center gap-2">
                {b.demand_signals_created > 0 && <Badge variant="accent">{b.demand_signals_created} demand signal(s)</Badge>}
                <Button size="sm" onClick={() => refresh(b.id)}>
                  <RefreshCw size={13} /> Refresh
                </Button>
              </div>
            </div>
            {b.transcripts.map((t, i) => (
              <div key={i} className="mt-3 rounded-md bg-black/[0.02] p-3 text-sm">
                <p className="mb-1 text-xs text-ink-faint">
                  {t.file} {t.language && <Badge variant="voice" className="ml-1">{nativeName(t.language) || t.language}</Badge>}
                </p>
                {t.segments.length ? (
                  <ul className="space-y-1">
                    {t.segments.map((s, j) => (
                      <li key={j}>
                        <span className="mr-2 font-mono text-[11px] text-accent">{s.speaker ?? "?"}</span>
                        {s.text}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>{t.full_transcript}</p>
                )}
              </div>
            ))}
            {b.error && <p className="mt-2 text-xs text-danger">{b.error}</p>}
          </div>
        ))}
      </CardBody>
    </Card>
  );
}
