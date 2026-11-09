"use client";

// Browser audio for Gnani:
//  - MicRecorder: captures the microphone, downsamples to 16 kHz 16-bit mono
//    PCM (what Gnani Prisma wants), reports a live level for the waveform,
//    and can stream frames (realtime) or hand back a WAV (push-to-talk).
//  - PcmPlayer: plays Timbre's streamed raw PCM chunks gaplessly, so speech
//    starts on the first chunk instead of after the whole sentence.

export const STT_SAMPLE_RATE = 16000;

const WORKLET = `
class Tap extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) this.port.postMessage(ch.slice(0));
    return true;
  }
}
registerProcessor("gnani-tap", Tap);
`;

function downsample(input: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (fromRate === toRate) return input;
  const ratio = fromRate / toRate;
  const out = new Float32Array(Math.floor(input.length / ratio));
  for (let i = 0; i < out.length; i++) {
    // average the source samples that map to this output sample (simple low-pass)
    const start = Math.floor(i * ratio);
    const end = Math.min(input.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end; j++) sum += input[j];
    out[i] = sum / Math.max(1, end - start);
  }
  return out;
}

function toInt16(f: Float32Array): Int16Array {
  const out = new Int16Array(f.length);
  for (let i = 0; i < f.length; i++) {
    const s = Math.max(-1, Math.min(1, f[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

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

export class MicRecorder {
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: AudioWorkletNode | null = null;
  private chunks: Int16Array[] = [];
  private startedAt = 0;

  constructor(
    private readonly onLevel: (level: number) => void = () => {},
    private readonly onFrame: ((pcm: Int16Array) => void) | null = null
  ) {}

  static supported(): boolean {
    return typeof window !== "undefined" && !!navigator.mediaDevices?.getUserMedia && "AudioWorkletNode" in window;
  }

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    this.ctx = new AudioContext();
    const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
    await this.ctx.audioWorklet.addModule(url);
    URL.revokeObjectURL(url);
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.ctx, "gnani-tap");
    const rate = this.ctx.sampleRate;
    this.node.port.onmessage = (e: MessageEvent<Float32Array>) => {
      const f = e.data;
      let sum = 0;
      for (let i = 0; i < f.length; i++) sum += f[i] * f[i];
      this.onLevel(Math.min(1, Math.sqrt(sum / f.length) * 4));
      const pcm = toInt16(downsample(f, rate, STT_SAMPLE_RATE));
      this.chunks.push(pcm);
      this.onFrame?.(pcm);
    };
    src.connect(this.node);
    this.chunks = [];
    this.startedAt = performance.now();
  }

  seconds(): number {
    return this.startedAt ? (performance.now() - this.startedAt) / 1000 : 0;
  }

  /** Stops the mic and returns everything recorded as one 16 kHz WAV. */
  async stop(): Promise<Blob> {
    this.node?.port.close();
    this.node?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    await this.ctx?.close().catch(() => {});
    this.ctx = null;
    const total = this.chunks.reduce((n, c) => n + c.length, 0);
    const all = new Int16Array(total);
    let off = 0;
    for (const c of this.chunks) {
      all.set(c, off);
      off += c.length;
    }
    this.chunks = [];
    this.onLevel(0);
    return encodeWav(all);
  }
}

export class PcmPlayer {
  private ctx: AudioContext | null = null;
  private nextTime = 0;
  private sources: AudioBufferSourceNode[] = [];
  private leftover: Uint8Array | null = null;
  onEnded: (() => void) | null = null;

  private ensure(): AudioContext {
    if (!this.ctx) this.ctx = new AudioContext();
    return this.ctx;
  }

  /** Queue one chunk of 16-bit little-endian mono PCM. */
  enqueue(bytes: Uint8Array, sampleRate: number): void {
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
    const samples = new Int16Array(data.buffer, data.byteOffset, data.length / 2);
    if (!samples.length) return;
    const buf = ctx.createBuffer(1, samples.length, sampleRate);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < samples.length; i++) ch[i] = samples[i] / 0x8000;
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    const at = Math.max(ctx.currentTime + 0.03, this.nextTime);
    src.start(at);
    this.nextTime = at + buf.duration;
    this.sources.push(src);
    src.onended = () => {
      this.sources = this.sources.filter((s) => s !== src);
      if (this.sources.length === 0) this.onEnded?.();
    };
  }

  stop(): void {
    for (const s of this.sources) {
      try {
        s.stop();
      } catch {
        // already stopped
      }
    }
    this.sources = [];
    this.nextTime = 0;
  }
}

export async function playBlob(blob: Blob): Promise<void> {
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  await new Promise<void>((resolve, reject) => {
    audio.onended = () => resolve();
    audio.onerror = () => reject(new Error("Could not play audio"));
    audio.play().catch(reject);
  });
  URL.revokeObjectURL(url);
}
