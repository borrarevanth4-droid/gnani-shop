"""The single choke point for every call to Gnani Vachana.

Same design as the LLM gateway (app/llm/gateway.py), for the same reasons:
nothing else in the codebase talks to api.vachana.ai. Everything — speech to
text (REST, batch), text to speech (sync, streaming), voice cloning — goes
through one `VoiceGateway` instance, which owns:

- retry with exponential backoff, but only for retryable failures
  (429 rate-limited, 5xx, timeouts). A bad key or bad input is never retried.
- a circuit breaker per capability (STT / TTS): after repeated failures we
  stop paying the full timeout on every request and fail fast for a cooldown
  window, so the app falls back to typed chat immediately.
- chaos faults (development only) that flow through the exact same paths.
- latency and cost accounting returned with every result, so the audit log
  and the Voice Insights page can show real numbers.

Realtime streaming STT (WebSocket) lives in app/voice/realtime.py but takes
its URL, key and breaker from here.
"""

import base64
import json
import time
from collections.abc import Iterator
from dataclasses import dataclass, field

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.llm.circuit_breaker import CircuitBreaker
from app.testing.chaos import ChaosFault, is_active

# Gnani's edge (Cloudflare) rejects requests with a generic library
# User-Agent ("error code: 1010"). Identify the client honestly instead.
USER_AGENT = "gnani-shop/1.0 (+voice-commerce demo)"


class VoiceGatewayError(Exception):
    """A Gnani call failed after retries (or the breaker is open). `retryable`
    tells the caller whether trying again later could help."""

    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False, code: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.code = code


@dataclass
class SttResult:
    transcript: str
    detected_language: str | None
    model: str
    format: str
    processing_time_s: float | None
    end_to_end_latency_s: float | None
    latency_ms: int  # measured by us, round trip
    request_id: str | None = None
    audio_seconds: float | None = None
    cost_paise: int | None = None
    truncated: bool = False


@dataclass
class TtsResult:
    audio: bytes
    content_type: str
    model: str
    voice: str | None
    language: str | None
    characters: int
    latency_ms: int
    cost_paise: int | None = None


@dataclass
class TtsChunk:
    index: int
    audio: bytes
    is_final: bool


@dataclass
class BatchJob:
    job_id: str
    status: str
    raw: dict = field(default_factory=dict)


def _wav_seconds(audio: bytes) -> float | None:
    """Duration of a PCM WAV from its header, for cost accounting. None for
    anything we can't read — cost is then simply not computed."""
    try:
        if audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
            return None
        byte_rate = int.from_bytes(audio[28:32], "little")
        data_idx = audio.find(b"data", 12)
        if byte_rate <= 0 or data_idx < 0:
            return None
        data_len = int.from_bytes(audio[data_idx + 4 : data_idx + 8], "little")
        return round(data_len / byte_rate, 3)
    except Exception:  # noqa: BLE001
        return None


def pad_leading_silence(audio: bytes, seconds: float = 0.3) -> bytes:
    """Prepends silence to a 16-bit PCM WAV. A clip that starts the instant
    the speaker does can lose its first consonant ("పాలు" heard as "ఆలు");
    a short lead-in gives Prisma's voice-activity detection room to start.
    Anything that isn't a plain PCM WAV is returned unchanged."""
    try:
        if audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
            return audio
        byte_rate = int.from_bytes(audio[28:32], "little")
        block_align = int.from_bytes(audio[32:34], "little") or 2
        data_idx = audio.find(b"data", 12)
        if byte_rate <= 0 or data_idx < 0:
            return audio
        pad = b"\x00" * (int(byte_rate * seconds) // block_align * block_align)
        data_len = int.from_bytes(audio[data_idx + 4 : data_idx + 8], "little") + len(pad)
        riff_len = int.from_bytes(audio[4:8], "little") + len(pad)
        return (audio[:4] + riff_len.to_bytes(4, "little") + audio[8:data_idx + 4] + data_len.to_bytes(4, "little")
                + pad + audio[data_idx + 8:])
    except Exception:  # noqa: BLE001
        return audio


def _error_from_response(resp: httpx.Response) -> VoiceGatewayError:
    status = resp.status_code
    code = None
    message = resp.text[:300]
    try:
        body = resp.json()
        if isinstance(body.get("error"), dict):
            code = body["error"].get("type")
            message = body["error"].get("message") or message
        elif isinstance(body.get("detail"), dict):
            code = body["detail"].get("error_code")
            message = body["detail"].get("message") or message
        elif "code" in body:
            code = body.get("code")
            message = body.get("message") or message
        elif "message" in body:
            message = body["message"]
    except ValueError:
        pass
    retryable = status == 429 or status >= 500
    return VoiceGatewayError(f"Gnani {status}{f' {code}' if code else ''}: {message}", status_code=status,
                             retryable=retryable, code=code)


class VoiceGateway:
    def __init__(self) -> None:
        self.stt_breaker = CircuitBreaker(
            settings.gnani_circuit_breaker_failure_threshold, settings.gnani_circuit_breaker_cooldown_seconds
        )
        self.tts_breaker = CircuitBreaker(
            settings.gnani_circuit_breaker_failure_threshold, settings.gnani_circuit_breaker_cooldown_seconds
        )

    # ------------------------------------------------------------ plumbing

    @property
    def configured(self) -> bool:
        return bool(settings.gnani_api_key)

    def headers(self, extra: dict | None = None) -> dict:
        return {"X-API-Key-ID": settings.gnani_api_key, "User-Agent": USER_AGENT, **(extra or {})}

    def _client(self, timeout: float | None = None) -> httpx.Client:
        return httpx.Client(base_url=settings.gnani_base_url, timeout=timeout or settings.gnani_timeout_seconds)

    def _with_retries(self, breaker: CircuitBreaker, what: str, fn):
        if not self.configured:
            raise VoiceGatewayError("GNANI_API_KEY is not set — voice is unavailable.", code="NOT_CONFIGURED")
        if breaker.is_open():
            raise VoiceGatewayError(
                f"Gnani {what} is temporarily unavailable after repeated failures; using text until it recovers.",
                retryable=True, code="CIRCUIT_OPEN",
            )
        attempts = settings.gnani_max_retries + 1
        last: VoiceGatewayError | None = None
        for attempt in range(1, attempts + 1):
            try:
                result = fn()
                breaker.record_success()
                return result
            except httpx.TimeoutException as e:
                last = VoiceGatewayError(f"Gnani {what} timed out: {e}", retryable=True, code="TIMEOUT")
            except httpx.TransportError as e:
                last = VoiceGatewayError(f"Could not reach Gnani {what}: {e}", retryable=True, code="NETWORK")
            except VoiceGatewayError as e:
                last = e
            logger.warning(
                "gnani call failed",
                extra={"capability": what, "attempt": attempt, "status_code": last.status_code,
                       "code": last.code, "retryable": last.retryable},
            )
            if not last.retryable or attempt >= attempts:
                break
            time.sleep(0.5 * (2 ** (attempt - 1)))
        breaker.record_failure()
        raise last  # type: ignore[misc]

    # ------------------------------------------------------------ speech to text

    def transcribe(
        self,
        audio: bytes,
        *,
        filename: str = "speech.wav",
        language: str | None = None,
        fmt: str | None = None,
        model: str | None = None,
        keyterms: list[str] | None = None,
        topic: str | None = None,
        previous_text: str | None = None,
    ) -> SttResult:
        """Prisma REST transcription (clips up to 30 s)."""
        model = model or settings.gnani_stt_model
        fmt = fmt or settings.gnani_stt_format
        spoken_seconds = _wav_seconds(audio)  # the buyer's real audio, before padding
        audio = pad_leading_silence(audio)
        language = language or settings.gnani_stt_language
        data: dict[str, str] = {"model": model, "language_code": language, "format": fmt}
        if model == "prisma-v3.0":
            if keyterms:
                data["keyterms"] = json.dumps(keyterms[:200], ensure_ascii=False)
            if topic:
                data["topic"] = topic[:1600]
            if previous_text:
                data["previous_text"] = previous_text[-600:]

        def call() -> SttResult:
            if is_active(ChaosFault.GNANI_STT_TIMEOUT):
                raise VoiceGatewayError("Chaos: simulated Gnani STT timeout.", retryable=True, code="TIMEOUT")
            start = time.monotonic()
            if is_active(ChaosFault.GNANI_GARBLED_TRANSCRIPT):
                body = {"transcript": "", "model": model, "processing_time": 0.0, "end_to_end_latency": 0.0}
            else:
                with self._client() as client:
                    resp = client.post(
                        "/stt/v3",
                        headers=self.headers(),
                        data=data,
                        files={"audio_file": (filename, audio, "audio/wav")},
                    )
                if resp.status_code != 200:
                    raise _error_from_response(resp)
                body = resp.json()
            latency_ms = int((time.monotonic() - start) * 1000)
            seconds = spoken_seconds
            cost = round(seconds * settings.gnani_cost_paise_per_audio_second) if seconds is not None else None
            return SttResult(
                transcript=(body.get("transcript") or "").strip(),
                detected_language=body.get("detected_language_code"),
                model=body.get("model") or model,
                format=fmt,
                processing_time_s=body.get("processing_time"),
                end_to_end_latency_s=body.get("end_to_end_latency"),
                latency_ms=latency_ms,
                request_id=body.get("request_id"),
                audio_seconds=seconds,
                cost_paise=cost,
                truncated=bool(body.get("truncated")),
            )

        return self._with_retries(self.stt_breaker, "speech-to-text", call)

    # ------------------------------------------------------------ text to speech

    def _tts_body(
        self, text: str, *, voice: str | None, model: str, language: str | None, speed: float,
        sample_rate: int, container: str, speaker_embedding: dict | None = None,
    ) -> dict:
        audio_config = {
            "sample_rate": sample_rate,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": container,
        }
        if speaker_embedding is not None:
            return {"text": text, "model": "vachana-vc-v1", "audio_config": audio_config,
                    "speaker_embedding": speaker_embedding}
        return {
            "text": text,
            "voice": voice,
            "model": model,
            "language": language or "auto",
            "speed": speed,
            "audio_config": audio_config,
        }

    def synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,
        model: str | None = None,
        language: str | None = None,
        speed: float = 1.0,
        sample_rate: int | None = None,
        container: str = "wav",
        speaker_embedding: dict | None = None,
    ) -> TtsResult:
        """Timbre synchronous synthesis: the whole clip in one response."""
        model = model or settings.gnani_tts_model
        voice = voice or settings.gnani_tts_voice
        sample_rate = sample_rate or settings.gnani_tts_sample_rate
        if speaker_embedding is not None:
            sample_rate = min(sample_rate, 44100)
        body = self._tts_body(text, voice=voice, model=model, language=language, speed=speed,
                              sample_rate=sample_rate, container=container, speaker_embedding=speaker_embedding)

        def call() -> TtsResult:
            if is_active(ChaosFault.GNANI_TTS_FAILURE):
                raise VoiceGatewayError("Chaos: simulated Gnani TTS failure.", status_code=503, retryable=True,
                                        code="SERVICE_UNAVAILABLE")
            start = time.monotonic()
            with self._client() as client:
                resp = client.post("/api/v1/tts/inference", headers=self.headers({"Content-Type": "application/json"}),
                                   content=json.dumps(body, ensure_ascii=False).encode("utf-8"))
            if resp.status_code != 200:
                raise _error_from_response(resp)
            return TtsResult(
                audio=resp.content,
                content_type=resp.headers.get("content-type", "audio/wav"),
                model=body.get("model", model),
                voice=body.get("voice"),
                language=body.get("language"),
                characters=len(text),
                latency_ms=int((time.monotonic() - start) * 1000),
                cost_paise=round(len(text) * settings.gnani_cost_paise_per_tts_char),
            )

        return self._with_retries(self.tts_breaker, "text-to-speech", call)

    def synthesize_stream(
        self,
        text: str,
        *,
        voice: str | None = None,
        model: str | None = None,
        language: str | None = None,
        speed: float = 1.0,
        sample_rate: int | None = None,
    ) -> Iterator[TtsChunk]:
        """Timbre SSE streaming: yields raw 16-bit mono PCM chunks as soon as
        Gnani produces them, so playback can start before the whole sentence
        is synthesised. Retries/breaker cover establishing the stream; a
        failure mid-stream ends it (the caller falls back to text)."""
        model = model or settings.gnani_tts_model
        voice = voice or settings.gnani_tts_voice
        sample_rate = sample_rate or settings.gnani_tts_sample_rate
        body = self._tts_body(text, voice=voice, model=model, language=language, speed=speed,
                              sample_rate=sample_rate, container="raw")

        def open_stream():
            if is_active(ChaosFault.GNANI_TTS_FAILURE):
                raise VoiceGatewayError("Chaos: simulated Gnani TTS failure.", status_code=503, retryable=True,
                                        code="SERVICE_UNAVAILABLE")
            client = httpx.Client(base_url=settings.gnani_base_url,
                                  timeout=httpx.Timeout(settings.gnani_timeout_seconds, read=60.0))
            req = client.build_request("POST", "/api/v1/tts/sse",
                                       headers=self.headers({"Content-Type": "application/json",
                                                             "Accept": "text/event-stream"}),
                                       content=json.dumps(body, ensure_ascii=False).encode("utf-8"))
            resp = client.send(req, stream=True)
            if resp.status_code != 200:
                resp.read()
                client.close()
                raise _error_from_response(resp)
            return client, resp

        client, resp = self._with_retries(self.tts_breaker, "text-to-speech", open_stream)
        try:
            event = None
            for line in resp.iter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    payload = json.loads(line[5:].strip() or "{}")
                    if event == "error":
                        raise VoiceGatewayError(f"Gnani TTS stream error: {payload.get('message')}", code="STREAM_ERROR")
                    if event in ("chunk", "complete"):
                        audio_b64 = payload.get("audio") or ""
                        yield TtsChunk(
                            index=int(payload.get("chunk_index") or 0),
                            audio=base64.b64decode(audio_b64) if audio_b64 else b"",
                            is_final=bool(payload.get("is_final")) or event == "complete",
                        )
                        if event == "complete":
                            return
        finally:
            resp.close()
            client.close()

    # ------------------------------------------------------------ voice cloning

    def clone_embedding(self, audio: bytes, filename: str = "reference.wav") -> dict:
        """Reference audio (5–30 s) → a speaker embedding dict usable as
        `speaker_embedding` in synthesis. Store it; never re-clone per call."""

        def call() -> dict:
            with self._client(timeout=60.0) as client:
                resp = client.post("/api/v1/tts/voice-clone/embeddings", headers=self.headers(),
                                   files={"audio_file": (filename, audio, "audio/wav")})
            if resp.status_code != 200:
                raise _error_from_response(resp)
            emb = (resp.json().get("data") or {}).get("voice_clone_embedding")
            if not emb or not emb.get("embedding"):
                raise VoiceGatewayError("Gnani returned no voice embedding.", code="NO_EMBEDDING")
            return {"embedding": emb["embedding"], "shape": emb.get("shape", [1, 768]),
                    "dtype": emb.get("dtype", "torch.bfloat16")}

        return self._with_retries(self.tts_breaker, "voice-cloning", call)

    # ------------------------------------------------------------ batch STT (call recordings)

    def batch_create_and_start(
        self, files: list[tuple[str, bytes]], *, language: str = "indic-auto", with_diarization: bool = True,
        num_speakers: int = 2,
    ) -> BatchJob:
        config = {
            "model": settings.gnani_stt_model,
            "language_code": language,
            "mode": "transcribe",
            "with_diarization": with_diarization,
            "num_speakers": num_speakers,
            "is_multi_channel": False,
        }

        def call() -> BatchJob:
            with self._client(timeout=120.0) as client:
                resp = client.post(
                    "/stt/v3/batch/jobs",
                    headers=self.headers(),
                    data={"config": json.dumps(config)},
                    files=[("files", (name, data, "audio/wav")) for name, data in files],
                )
                if resp.status_code not in (200, 201):
                    raise _error_from_response(resp)
                job_id = resp.json()["job_id"]
                start = client.post(f"/stt/v3/batch/jobs/{job_id}/start", headers=self.headers())
                if start.status_code not in (200, 201, 202):
                    raise _error_from_response(start)
            return BatchJob(job_id=job_id, status="STARTED", raw=resp.json())

        return self._with_retries(self.stt_breaker, "batch speech-to-text", call)

    def batch_status(self, job_id: str) -> BatchJob:
        def call() -> BatchJob:
            with self._client() as client:
                resp = client.get(f"/stt/v3/batch/jobs/{job_id}", headers=self.headers())
            if resp.status_code != 200:
                raise _error_from_response(resp)
            body = resp.json()
            return BatchJob(job_id=job_id, status=body.get("status", "UNKNOWN"), raw=body)

        return self._with_retries(self.stt_breaker, "batch speech-to-text", call)

    def batch_transcripts(self, job_id: str) -> list[dict]:
        """Completed files' transcript JSON (segments with speaker_id, full_transcript)."""

        def call() -> list[dict]:
            out: list[dict] = []
            with self._client(timeout=60.0) as client:
                resp = client.get(f"/stt/v3/batch/jobs/{job_id}/files", headers=self.headers(),
                                  params={"status": "COMPLETED", "limit": 100})
                if resp.status_code != 200:
                    raise _error_from_response(resp)
                for f in resp.json().get("data", []):
                    url = f.get("transcript_url")
                    if not url:
                        continue
                    t = httpx.get(url, timeout=60.0, headers={"User-Agent": USER_AGENT})
                    if t.status_code == 200:
                        out.append(t.json())
            return out

        return self._with_retries(self.stt_breaker, "batch speech-to-text", call)

    def status(self) -> dict:
        return {
            "configured": self.configured,
            "stt_available": not self.stt_breaker.is_open(),
            "tts_available": not self.tts_breaker.is_open(),
            "stt_model": settings.gnani_stt_model,
            "tts_model": settings.gnani_tts_model,
            "default_voice": settings.gnani_tts_voice,
        }


voice_gateway = VoiceGateway()
