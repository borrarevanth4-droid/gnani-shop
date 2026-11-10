"use client";

// Browser audio for Gnani:
//  - One shared AudioContext for the whole page. It is unlocked (resumed) inside
//    a click, so the browser's autoplay rules never mute a reply, and it is never
//    re-created per turn (browsers cap how many contexts a page may open).
//  - MicRecorder: captures the microphone and resamples to 16 kHz 16-bit mono
//    PCM (what Gnani Prisma wants) INSIDE the audio worklet, with a resampler that
//    keeps its position across frames, so there are no clicks or speed-up. It
//    emits 20 ms frames, keeps a short pre-roll so the first syllable is never
//    cut, and can stay open for a whole conversation.
//  - VoiceActivityDetector: decides when you started and stopped talking, from
//    the audio frames themselves (not animation frames, which pause in
//    background tabs), with a noise floor that adapts instead of being guessed
//    from the first 350 ms.
//  - PcmPlayer: plays Timbre's streamed raw PCM chunks gaplessly.

export const STT_SAMPLE_RATE = 16000;
const FRAME_SAMPLES = 320; // 20 ms at 16 kHz
const PREROLL_FRAMES = 20; // 400 ms kept from before speech is detected

// ------------------------------------------------------------ shared context

let sharedCtx: AudioContext | null = null;

export function audioContext(): AudioContext {
  if (!sharedCtx || sharedCtx.state === "closed") {
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    sharedCtx = new Ctor({ latencyHint: "interactive" });
  }
  return sharedCtx;
}

/** Call synchronously inside a click/tap handler so later playback is allowed. */
export function unlockAudio(): void {
  try {
    const ctx = audioContext();
    if (ctx.state === "suspended") void ctx.resume();
    // A one-sample silent buffer fully unlocks iOS Safari.
    const b = ctx.createBuffer(1, 1, ctx.sampleRate);
    const s = ctx.createBufferSource();
    s.buffer = b;
    s.connect(ctx.destination);
    s.start(0);
  } catch {
    // no audio support; callers fall back to text
  }
}

async function running(ctx: AudioContext): Promise<void> {
  if (ctx.state === "suspended") await ctx.resume().catch(() => {});
}

// ------------------------------------------------------------ worklet

// Runs on the audio thread. Linear-interpolation resampler from the device
// rate (44.1/48 kHz) to 16 kHz with a one-pole low-pass in front to tame
// aliasing; carries its fractional read position and last sample across the
// 128-sample render quanta, then posts fixed 20 ms Int16 frames + RMS level.
const WORKLET = `
class GnaniTap extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / ${STT_SAMPLE_RATE};
    this.pos = 0;          // fractional read position into the current block
    this.prev = 0;         // last filtered sample of the previous block
    this.lp = 0;           // low-pass state
    this.alpha = Math.min(1, (2 * Math.PI * 7000) / sampleRate / (1 + (2 * Math.PI * 7000) / sampleRate));
    this.out = new Int16Array(${FRAME_SAMPLES});
    this.n = 0;
    this.sq = 0;
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    const len = ch.length;
    const f = new Float32Array(len);
    for (let i = 0; i < len; i++) { this.lp += this.alpha * (ch[i] - this.lp); f[i] = this.lp; }
    // pos is measured from "prev" (index -1) so interpolation crosses block edges.
    while (this.pos < len) {
      const i = Math.floor(this.pos);
      const frac = this.pos - i;
      const a = i === 0 ? this.prev : f[i - 1];
      const b = f[i];
      let s = a + (b - a) * frac;
      s = s > 1 ? 1 : s < -1 ? -1 : s;
      this.sq += s * s;
      this.out[this.n++] = s < 0 ? s * 0x8000 : s * 0x7fff;
      if (this.n === ${FRAME_SAMPLES}) {
        const rms = Math.sqrt(this.sq / ${FRAME_SAMPLES});
        this.port.postMessage({ pcm: this.out.slice(0), rms });
        this.n = 0; this.sq = 0;
      }
      this.pos += this.ratio;
    }
    this.pos -= len;
    this.prev = f[len - 1];
    return true;
  }
}
registerProcessor("gnani-tap", GnaniTap);
`;

const workletLoaded = new WeakSet<AudioContext>();

async function ensureWorklet(ctx: AudioContext): Promise<void> {
  if (workletLoaded.has(ctx)) return;
  const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
  try {
    await ctx.audioWorklet.addModule(url);
    workletLoaded.add(ctx);
  } finally {
    URL.revokeObjectURL(url);
  }
}

// ------------------------------------------------------------ WAV

export function encodeWav(samples: Int16Array, sampleRate = STT_SAMPLE_RATE): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buffer);
  const w = (o: number, s: string) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  w(0, "RIFF");
  v.setUint32(4, 36 + samples.length * 2, true);
  w(8, "WAVE");
  w(12, "fmt ");
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true);
  v.setUint16(22, 1, true);
  v.setUint32(24, sampleRate, true);
  v.setUint32(28, sampleRate * 2, true);
  v.setUint16(32, 2, true);
  v.setUint16(34, 16, true);
  w(36, "data");
  v.setUint32(40, samples.length * 2, true);
  new Int16Array(buffer, 44).set(samples);
  return new Blob([buffer], { type: "audio/wav" });
}

function concat(chunks: Int16Array[]): Int16Array {
  const all = new Int16Array(chunks.reduce((n, c) => n + c.length, 0));
  let off = 0;
  for (const c of chunks) {
    all.set(c, off);
    off += c.length;
  }
  return all;
}

// ------------------------------------------------------------ mic

/** Level shown in the UI and used by the VAD: RMS × 4, clipped to 0..1. */
const toLevel = (rms: number) => Math.min(1, rms * 4);

export class MicRecorder {
  private stream: MediaStream | null = null;
  private src: MediaStreamAudioSourceNode | null = null;
  private node: AudioWorkletNode | null = null;
  private sink: GainNode | null = null;
  private chunks: Int16Array[] = [];
  private preroll: Int16Array[] = [];
  private startedAt = 0;
  private recording = false;

  constructor(
    private readonly onLevel: (level: number) => void = () => {},
    private readonly onFrame: ((pcm: Int16Array, level: number) => void) | null = null
  ) {}

  static supported(): boolean {
    return typeof window !== "undefined" && !!navigator.mediaDevices?.getUserMedia && "AudioWorkletNode" in window;
  }

  get open(): boolean {
    return !!this.stream;
  }

  /** Opens the mic (once) and starts a fresh recording. */
  async start(): Promise<void> {
    if (!this.stream) {
      const ctx = audioContext();
      await running(ctx);
      await ensureWorklet(ctx);
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      this.src = ctx.createMediaStreamSource(this.stream);
      this.node = new AudioWorkletNode(ctx, "gnani-tap", { numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1] });
      // Some browsers only run a worklet that reaches the destination; route it
      // through a muted gain so it is pulled without being heard.
      this.sink = ctx.createGain();
      this.sink.gain.value = 0;
      this.node.port.onmessage = (e: MessageEvent<{ pcm: Int16Array; rms: number }>) => {
        const { pcm, rms } = e.data;
        const level = toLevel(rms);
        this.onLevel(level);
        if (this.recording) this.chunks.push(pcm);
        else {
          this.preroll.push(pcm);
          if (this.preroll.length > PREROLL_FRAMES) this.preroll.shift();
        }
        this.onFrame?.(pcm, level);
      };
      this.src.connect(this.node);
      this.node.connect(this.sink);
      this.sink.connect(audioContext().destination);
    }
    this.begin();
  }

  /** Start a new utterance on an already-open mic, keeping the pre-roll. */
  begin(): void {
    this.chunks = [...this.preroll];
    this.preroll = [];
    this.recording = true;
    this.startedAt = performance.now();
  }

  /** Stop recording but keep the mic open (for the next turn). */
  take(): Blob {
    this.recording = false;
    const wav = encodeWav(concat(this.chunks));
    this.chunks = [];
    this.preroll = [];
    return wav;
  }

  seconds(): number {
    return this.recording && this.startedAt ? (performance.now() - this.startedAt) / 1000 : 0;
  }

  /** Stops the mic and returns everything recorded as one 16 kHz WAV. */
  async stop(): Promise<Blob> {
    const wav = this.take();
    if (this.node) {
      this.node.port.onmessage = null;
      this.node.port.close();
    }
    this.src?.disconnect();
    this.node?.disconnect();
    this.sink?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = this.src = this.node = this.sink = null;
    this.onLevel(0);
    return wav;
  }
}

// ------------------------------------------------------------ VAD

export interface VadOptions {
  minThreshold: number; // never trigger below this level
  floorMultiplier: number; // speech = this many times above the noise floor
  speechConfirmMs: number; // continuous voice needed to count as speech
  endSilenceMs: number; // quiet after speech = you've finished
  noSpeechTimeoutMs: number;
  maxTurnMs: number; // Prisma REST accepts up to 30 s
  ignoreMs: number; // ignore the first bit (button click, tail of the reply)
}

export const DEFAULT_VAD: VadOptions = {
  minThreshold: 0.06,
  floorMultiplier: 3,
  speechConfirmMs: 120,
  endSilenceMs: 900,
  noSpeechTimeoutMs: 9000,
  maxTurnMs: 25000,
  ignoreMs: 150,
};

export type VadEvent = "none" | "speech_start" | "end" | "no_speech";

/** Frame-driven voice-activity detector. Feed it every 20 ms frame's level. */
export class VoiceActivityDetector {
  private t = 0;
  private noise = 0.015;
  private recent: number[] = []; // last ~1.5 s of levels
  private voicedRun = 0;
  private voicedTotal = 0;
  private silence = 0;
  private speechLevel = 0; // loudest level heard while voiced
  speech = false;

  constructor(private readonly o: VadOptions = DEFAULT_VAD) {}

  reset(): void {
    this.t = 0;
    this.voicedRun = 0;
    this.voicedTotal = 0;
    this.silence = 0;
    this.speech = false;
    this.speechLevel = 0;
    this.recent = [];
    // keep the learned noise floor between turns
  }

  push(level: number, frameMs = 20): VadEvent {
    this.t += frameMs;
    // Noise floor = quietest level of the last 1.5 s (speech always has gaps
    // between words; steady background noise does not), capped so loud
    // speech can never become "noise".
    this.recent.push(level);
    if (this.recent.length > 1500 / frameMs) this.recent.shift();
    if (this.recent.length >= 300 / frameMs) this.noise = Math.min(0.12, Math.min(...this.recent));
    if (this.t <= this.o.ignoreMs) return "none";

    if (!this.speech) {
      const threshold = Math.max(this.o.minThreshold, this.noise * this.o.floorMultiplier);
      if (level > threshold) {
        this.voicedRun += frameMs;
        this.voicedTotal += frameMs;
        this.speechLevel = Math.max(this.speechLevel, level);
      } else this.voicedRun = 0;
      if (this.voicedRun >= this.o.speechConfirmMs) {
        this.speech = true;
        this.silence = 0;
        return "speech_start";
      }
    } else {
      // "Quiet" = back near the room noise, or far below how loud you speak.
      const quiet = Math.max(this.o.minThreshold, this.noise * 1.5, this.speechLevel * 0.25);
      if (level > quiet) {
        this.silence = 0;
        this.voicedTotal += frameMs;
        this.speechLevel = Math.max(this.speechLevel, Math.min(level, this.speechLevel * 1.5 || level));
      } else this.silence += frameMs;
      if (this.silence >= this.o.endSilenceMs) return "end";
    }
    if (this.t >= this.o.maxTurnMs) return this.speech || this.voicedTotal >= 250 ? "end" : "no_speech";
    if (!this.speech && this.t >= this.o.noSpeechTimeoutMs) return this.voicedTotal >= 250 ? "end" : "no_speech";
    return "none";
  }
}

// ------------------------------------------------------------ player

export class PcmPlayer {
  // Plays Timbre's streamed PCM gaplessly on the shared AudioContext.
  // "Finished" means BOTH that the stream has fully arrived (markComplete) AND
  // every queued buffer has played — a short network gap between chunks must
  // never look like the end of the reply.
  private nextTime = 0;
  private sources: AudioBufferSourceNode[] = [];
  private leftover: Uint8Array | null = null;
  private complete = false;
  private stopped = false;
  private waiters: (() => void)[] = [];
  private gain: GainNode | null = null;
  onEnded: (() => void) | null = null;

  private ensure(): AudioContext {
    const ctx = audioContext();
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
    if (!this.gain) {
      this.gain = ctx.createGain();
      this.gain.connect(ctx.destination);
    }
    return ctx;
  }

  private maybeFinish(): void {
    if ((this.complete && this.sources.length === 0) || this.stopped) {
      const w = this.waiters;
      this.waiters = [];
      w.forEach((fn) => fn());
      this.onEnded?.();
      this.onEnded = null;
    }
  }

  /** Queue one chunk of 16-bit little-endian mono PCM. */
  enqueue(bytes: Uint8Array, sampleRate: number): void {
    if (this.stopped) return;
    const ctx = this.ensure();
    let data = bytes;
    if (this.leftover) {
      const merged = new Uint8Array(this.leftover.length + bytes.length);
      merged.set(this.leftover);
      merged.set(bytes, this.leftover.length);
      data = merged;
      this.leftover = null;
    }
    if (data.length % 2 === 1) {
      this.leftover = data.slice(data.length - 1);
      data = data.slice(0, data.length - 1);
    }
    const copy = new Uint8Array(data); // aligned copy for Int16Array
    const samples = new Int16Array(copy.buffer, 0, copy.length / 2);
    if (!samples.length) return;
    const buf = ctx.createBuffer(1, samples.length, sampleRate);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < samples.length; i++) ch[i] = samples[i] / 0x8000;
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(this.gain!);
    // A small lead on the first chunk absorbs network jitter between chunks;
    // if the stream ever falls behind, restart with the same lead.
    const lead = this.nextTime < ctx.currentTime ? 0.12 : 0;
    const at = Math.max(ctx.currentTime + lead, this.nextTime);
    src.start(at);
    this.nextTime = at + buf.duration;
    this.sources.push(src);
    src.onended = () => {
      this.sources = this.sources.filter((x) => x !== src);
      this.maybeFinish();
    };
  }

  /** The stream has delivered its last chunk. */
  markComplete(): void {
    this.complete = true;
    this.maybeFinish();
  }

  /** Resolves when everything has been heard (or playback was stopped). */
  finished(): Promise<void> {
    if ((this.complete && this.sources.length === 0) || this.stopped) return Promise.resolve();
    return new Promise((resolve) => this.waiters.push(resolve));
  }

  stop(): void {
    if (this.stopped) return;
    this.stopped = true;
    for (const x of this.sources) {
      try {
        x.onended = null;
        x.stop();
      } catch {
        // already stopped
      }
    }
    this.sources = [];
    this.nextTime = 0;
    this.gain?.disconnect();
    this.gain = null;
    this.maybeFinish();
  }
}

export async function playBlob(blob: Blob): Promise<void> {
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  try {
    await new Promise<void>((resolve, reject) => {
      audio.onended = () => resolve();
      audio.onerror = () => reject(new Error("Could not play audio"));
      audio.play().catch(reject);
    });
  } finally {
    URL.revokeObjectURL(url);
  }
}
