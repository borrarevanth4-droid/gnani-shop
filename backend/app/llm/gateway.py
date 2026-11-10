"""The single choke point for every model call in the codebase.

Nothing else — not the harness, not the tools — talks to an LLM SDK or a
provider API directly. Everything goes through `gateway.call(...)`.

The provider is configuration, not code: `LLM_PROVIDER=groq` (default) or
`LLM_PROVIDER=nvidia`. Both expose the same OpenAI-compatible wire format,
so Agno's `OpenAILike` model is used purely as a typed HTTP transport (it
wraps the `openai` SDK and classifies provider errors with a status code,
which is what makes retry logic clean).
Agno's own agentic loop (`Agent.run()` / `Model.response()`) is deliberately
NOT used — it auto-executes tool calls, which would bypass the policy gate.
`Model.invoke()` is the lower-level primitive: one call in, one proposed
response out, nothing executed. The harness stays in full control.

Two resilience mechanisms live here, each with its own reason:
- Retry + fallback (the agent + policy engine): a single flaky call shouldn't fail the request.
- Circuit breaker (resilience): repeated failures shouldn't keep paying the
  full retry+timeout cost on every single request while a model is down —
  after enough consecutive failures, fail fast for a cooldown window instead.
"""

import json
import time
from dataclasses import dataclass

from agno.exceptions import ModelAuthenticationError, ModelProviderError
from agno.metrics import MessageMetrics
from agno.models.message import Message
from agno.models.openai.like import OpenAILike
from agno.models.response import ModelResponse

from app.core.config import settings
from app.core.logging import logger
from app.llm.circuit_breaker import CircuitBreaker
from app.testing.chaos import ChaosFault, is_active


class GatewayError(Exception):
    """Raised when both the primary and fallback models fail."""


# Per provider: (base URL setting, API key setting, default primary, default fallback).
# Groq and NVIDIA NIM both serve OpenAI's open-weight gpt-oss family, so the
# same prompts and tool schemas work unchanged on either.
_PROVIDERS: dict[str, dict[str, str]] = {
    "groq": {
        "base_url": settings.groq_base_url,
        "api_key": settings.groq_api_key,
        "primary": "openai/gpt-oss-120b",
        "fallback": "openai/gpt-oss-20b",
    },
    "nvidia": {
        "base_url": settings.nvidia_base_url,
        "api_key": settings.nvidia_api_key,
        # NVIDIA retired openai/gpt-oss-120b on 2026-09-03; Nemotron is the
        # primary there. Check https://integrate.api.nvidia.com/v1/models if
        # a call ever fails with "model not found" — NIM's catalog changes.
        "primary": "nvidia/nemotron-3.5-lightning-30b-a3b",
        "fallback": "openai/gpt-oss-20b",
    },
}


def _provider(name: str) -> dict[str, str]:
    name = (name or "groq").strip().lower()
    if name not in _PROVIDERS:
        raise ValueError(f"Unknown LLM provider '{name}'. Use one of: {', '.join(_PROVIDERS)}.")
    cfg = dict(_PROVIDERS[name])
    cfg["name"] = name
    return cfg


def provider_config() -> dict[str, str]:
    """Primary and fallback can live on DIFFERENT providers
    (LLM_FALLBACK_PROVIDER). Measured on this project's own multilingual
    prompts, Groq's gpt-oss-120b was the most accurate and fastest (0.5–1.4 s)
    but its free tier is limited to 8,000 tokens/minute; NVIDIA's Nemotron
    3.5 Lightning was slower (~5 s) but on a separate quota. Pairing them means
    a rate-limited turn moves to the other provider instead of waiting."""
    primary = _provider(settings.llm_provider)
    fallback = _provider(settings.llm_fallback_provider or settings.llm_provider)
    return {
        "name": primary["name"],
        "base_url": primary["base_url"],
        "api_key": primary["api_key"],
        "primary": settings.llm_model or primary["primary"],
        "fallback_provider": fallback["name"],
        "fallback": settings.llm_fallback or (
            fallback["primary"] if fallback["name"] != primary["name"] else primary["fallback"]
        ),
        "last_resort_provider": settings.llm_last_resort_provider or "",
        "last_resort": (
            settings.llm_last_resort_model or _provider(settings.llm_last_resort_provider)["primary"]
            if settings.llm_last_resort_provider
            else ""
        ),
    }


def make_model(model_id: str, *, timeout_seconds: float | None = None, provider: str | None = None) -> OpenAILike:
    """One OpenAI-compatible model handle. Also used by the cosmetic/low-stakes
    callers (titles, demand extraction, campaign copy) so there is exactly one
    place that knows about providers."""
    cfg = _provider(provider or settings.llm_provider)
    return OpenAILike(
        id=model_id,
        name=f"{cfg['name']}:{model_id}",
        provider=cfg["name"],
        api_key=cfg["api_key"] or "missing-key",
        base_url=cfg["base_url"],
        timeout=timeout_seconds or settings.llm_timeout_seconds,
        max_retries=0,
        # gpt-oss is a reasoning model; "low" keeps tool-calling turns fast.
        # Other models may reject the parameter, so it is sent only to gpt-oss.
        reasoning_effort="low" if "gpt-oss" in model_id else None,
    )


@dataclass
class ToolCall:
    id: str
    name: str
    arguments_raw: str  # unparsed JSON from the model — may be malformed


@dataclass
class GatewayResult:
    content: str | None
    tool_calls: list[ToolCall]
    model_used: str
    fallback_used: bool
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_paise: int | None = None


def _compute_cost_paise(total_tokens: int | None) -> int | None:
    if total_tokens is None:
        return None
    return round(total_tokens * settings.llm_cost_paise_per_token)


def _to_agno_messages(messages: list[dict]) -> list[Message]:
    return [
        Message(
            role=m["role"],
            content=m.get("content"),
            tool_calls=m.get("tool_calls"),
            tool_call_id=m.get("tool_call_id"),
            name=m.get("name"),
        )
        for m in messages
    ]


def _retry_after_seconds(error: Exception) -> float:
    """Providers on a tokens-per-minute plan (e.g. Groq's free tier) say how
    long to wait: "Please try again in 2.61s". Waiting that long — capped,
    so a turn never hangs — turns most rate-limit errors into a success on
    the next attempt instead of a burned retry."""
    import re

    m = re.search(r"try again in ([0-9.]+)\s*(ms|s)", str(error))
    if not m:
        return 0.0
    value = float(m.group(1)) / (1000 if m.group(2) == "ms" else 1)
    return min(value + 0.25, 12.0)


def _is_retryable(error: ModelProviderError) -> bool:
    classified = ModelProviderError.classify(error)
    status = classified.status_code
    return status == 429 or status >= 500


def _chaos_model_response() -> ModelResponse | None:
    """Returns a synthetic 'successful' model response standing in for the
    real API call, or None if no relevant fault is active. These bypass the
    real call entirely (deterministic, no network) but flow through the
    exact same downstream parsing as a real response — the harness can't
    tell the difference, which is the point: it exercises the real
    malformed-tool-call / hallucinated-SKU handling paths."""
    if is_active(ChaosFault.LLM_MALFORMED_TOOL_CALL):
        return ModelResponse(
            content=None,
            tool_calls=[
                {
                    "id": "chaos-malformed",
                    "type": "function",
                    "function": {"name": "add_to_cart", "arguments": '{"sku": "PET-001", "quantity": '},
                }
            ],
        )
    if is_active(ChaosFault.HALLUCINATE_SKU):
        return ModelResponse(
            content=None,
            tool_calls=[
                {
                    "id": "chaos-hallucinate",
                    "type": "function",
                    "function": {
                        "name": "add_to_cart",
                        "arguments": json.dumps({"sku": "CHAOS-FAKE-SKU-999", "quantity": 1}),
                    },
                }
            ],
        )
    return None


class LLMGateway:
    def __init__(
        self,
        primary_model_id: str,
        fallback_model_id: str,
        timeout_seconds: float,
        max_retries: int,
        backoff_base_seconds: float,
        circuit_breaker_failure_threshold: int,
        circuit_breaker_cooldown_seconds: float,
    ):
        self._primary_id = primary_model_id
        self._fallback_id = fallback_model_id
        self._max_retries = max_retries
        self._backoff_base = backoff_base_seconds
        self._primary = make_model(primary_model_id, timeout_seconds=timeout_seconds)
        self._fallback = make_model(fallback_model_id, timeout_seconds=timeout_seconds,
                                    provider=provider_config()["fallback_provider"])
        # Optional third model on its own quota (see Settings.llm_last_resort_provider).
        _cfg_lr = provider_config()
        self._last_resort = (
            make_model(_cfg_lr["last_resort"], timeout_seconds=timeout_seconds, provider=_cfg_lr["last_resort_provider"])
            if _cfg_lr["last_resort"]
            else None
        )
        self._last_resort_breaker = CircuitBreaker(circuit_breaker_failure_threshold, circuit_breaker_cooldown_seconds)
        self._primary_breaker = CircuitBreaker(circuit_breaker_failure_threshold, circuit_breaker_cooldown_seconds)
        self._fallback_breaker = CircuitBreaker(circuit_breaker_failure_threshold, circuit_breaker_cooldown_seconds)

    def call(self, messages: list[dict], tools: list[dict]) -> GatewayResult:
        agno_messages = _to_agno_messages(messages)

        if not self._primary_breaker.is_open():
            try:
                result = self._call_with_retries(self._primary, agno_messages, tools, fallback_used=False)
                self._primary_breaker.record_success()
                return result
            except GatewayError as primary_error:
                self._primary_breaker.record_failure()
                logger.warning(
                    "primary model exhausted, falling back",
                    extra={"primary_model": self._primary_id, "fallback_model": self._fallback_id, "error": str(primary_error)},
                )
        else:
            logger.warning(
                "primary model circuit breaker open, skipping straight to fallback",
                extra={"primary_model": self._primary_id, "consecutive_failures": self._primary_breaker.consecutive_failures},
            )

        if self._fallback_breaker.is_open():
            logger.error(
                "fallback model circuit breaker also open",
                extra={"fallback_model": self._fallback_id, "consecutive_failures": self._fallback_breaker.consecutive_failures},
            )
            if self._last_resort is None:
                raise GatewayError(
                    f"Both models are circuit-broken after repeated failures — failing fast without "
                    f"attempting a call. Will retry automatically after the cooldown window."
                )
        else:
            try:
                result = self._call_with_retries(self._fallback, agno_messages, tools, fallback_used=True,
                                                 hand_off=self._last_resort is not None)
                self._fallback_breaker.record_success()
                return result
            except GatewayError:
                self._fallback_breaker.record_failure()
                if self._last_resort is None:
                    raise

        # Last resort: a different provider's model, on its own quota.
        if self._last_resort_breaker.is_open():
            raise GatewayError("All configured models are unavailable right now. Please try again shortly.")
        try:
            result = self._call_with_retries(self._last_resort, agno_messages, tools, fallback_used=True)
            self._last_resort_breaker.record_success()
            return result
        except GatewayError:
            self._last_resort_breaker.record_failure()
            raise

    def call_low_priority(self, messages: list[dict], tools: list[dict]) -> GatewayResult:
        """For background jobs (conversation titles, demand extraction): use
        the last-resort model's separate quota first, so they never eat into
        the quota the live conversation needs. Falls back to the normal chain."""
        if self._last_resort is not None and not self._last_resort_breaker.is_open():
            try:
                result = self._call_with_retries(self._last_resort, _to_agno_messages(messages), tools,
                                                 fallback_used=True)
                self._last_resort_breaker.record_success()
                return result
            except GatewayError:
                self._last_resort_breaker.record_failure()
        return self.call(messages, tools)

    def _call_with_retries(
        self, model: OpenAILike, messages: list[Message], tools: list[dict], *, fallback_used: bool,
        hand_off: bool | None = None,
    ) -> GatewayResult:
        # Whether a long rate-limit wait should hand the turn to the next model
        # instead of sleeping. Default: the primary hands off, the last model waits.
        hand_off = (not fallback_used) if hand_off is None else hand_off
        last_error: Exception | None = None
        max_attempts = self._max_retries + 1

        for attempt in range(1, max_attempts + 1):
            assistant_message = Message(role="assistant")
            assistant_message.metrics = MessageMetrics()
            start = time.monotonic()

            try:
                chaos_response = _chaos_model_response()
                if chaos_response is not None:
                    model_response = chaos_response
                elif is_active(ChaosFault.SLOW_LLM):
                    # Stands in for a real timeout: same exception type and
                    # status class a genuine gateway timeout would raise, so
                    # it flows through the identical retry/backoff/fallback
                    # path below rather than a special case.
                    raise ModelProviderError(
                        message="Chaos: simulated LLM timeout", status_code=504, model_name=model.name, model_id=model.id
                    )
                else:
                    model_response = model.invoke(list(messages), assistant_message, tools=tools)
            except ModelAuthenticationError as e:
                logger.error(
                    "model call failed: authentication error (not retryable)",
                    extra={"model": model.id, "attempt": attempt, "fallback_used": fallback_used},
                )
                raise GatewayError(str(e)) from e
            except ModelProviderError as e:
                latency_ms = int((time.monotonic() - start) * 1000)
                retryable = _is_retryable(e)
                last_error = e
                logger.warning(
                    "model call failed",
                    extra={
                        "model": model.id,
                        "attempt": attempt,
                        "status_code": e.status_code,
                        "latency_ms": latency_ms,
                        "retryable": retryable,
                        "fallback_used": fallback_used,
                        "outcome": "error",
                    },
                )
                if not retryable or attempt >= max_attempts:
                    raise GatewayError(str(e)) from e
                wait = max(self._backoff_base * (2 ** (attempt - 1)), _retry_after_seconds(e))
                if e.status_code == 429 and wait > 3.0 and hand_off:
                    # Rate-limited for a while: hand the turn to the fallback
                    # (possibly another provider) now rather than make the
                    # buyer wait for this provider's quota to refill.
                    raise GatewayError(f"rate limited for {wait:.1f}s on {model.id}") from e
                time.sleep(wait)
                continue

            latency_ms = int((time.monotonic() - start) * 1000)
            tool_calls = [
                ToolCall(
                    id=tc.get("id", ""),
                    name=tc.get("function", {}).get("name", ""),
                    arguments_raw=tc.get("function", {}).get("arguments", "{}"),
                )
                for tc in (model_response.tool_calls or [])
            ]
            usage = model_response.response_usage
            # Agno's MessageMetrics.input_tokens/output_tokens/total_tokens are
            # parsed 1:1 from the raw OpenAI-compatible response's `usage` object
            # (usage.prompt_tokens/completion_tokens/total_tokens) — see
            # agno.models.openai.chat.OpenAIChat._get_metrics.
            prompt_tokens = getattr(usage, "input_tokens", None)
            completion_tokens = getattr(usage, "output_tokens", None)
            total_tokens = getattr(usage, "total_tokens", None)
            cost_paise = _compute_cost_paise(total_tokens)
            logger.info(
                "model call succeeded",
                extra={
                    "model": model.id,
                    "attempt": attempt,
                    "latency_ms": latency_ms,
                    "tool_call_count": len(tool_calls),
                    "fallback_used": fallback_used,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "cost_paise": cost_paise,
                    "outcome": "success",
                },
            )
            return GatewayResult(
                content=model_response.content,
                tool_calls=tool_calls,
                model_used=model.id,
                fallback_used=fallback_used,
                latency_ms=latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_paise=cost_paise,
            )

        raise GatewayError(f"exhausted {max_attempts} attempts on {model.id}: {last_error}")


_cfg = provider_config()
gateway = LLMGateway(
    primary_model_id=_cfg["primary"],
    fallback_model_id=_cfg["fallback"],
    timeout_seconds=settings.llm_timeout_seconds,
    max_retries=settings.llm_max_retries,
    backoff_base_seconds=settings.llm_retry_backoff_seconds,
    circuit_breaker_failure_threshold=settings.llm_circuit_breaker_failure_threshold,
    circuit_breaker_cooldown_seconds=settings.llm_circuit_breaker_cooldown_seconds,
)
