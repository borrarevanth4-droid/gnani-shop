from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> repo root is three levels up
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "gnani-shop"
    app_env: str = "development"
    log_level: str = "INFO"
    default_user_id: str = "user_demo"
    # The one canonical dev frontend origin — used for CORS, OAuth origin
    # validation, and every post-login redirect target. A single value, not a
    # list: `localhost` and `127.0.0.1` are different origins for cookies and
    # CORS even on the same machine and port. Pick one and use it everywhere.
    frontend_url: str = "http://127.0.0.1:3000"
    database_url: str = "sqlite:///./gnani_shop.db"

    # --- Agent brain: any OpenAI-compatible provider (see app/llm/gateway.py) ---
    # "groq" or "nvidia". Both serve the gpt-oss family over the same
    # OpenAI-compatible wire format, so switching is one line of config.
    llm_provider: str = "groq"
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    # Empty = the provider's default below (see _default_models()).
    llm_model: str = ""
    llm_fallback: str = ""
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 2
    llm_retry_backoff_seconds: float = 1.0
    # paise per token. cost_paise on every audit event is computed from this,
    # so it is real the day the rate is non-zero, with no code changes.
    llm_cost_paise_per_token: float = 0.0

    agent_max_iterations: int = 8

    # --- Gnani Vachana voice (see app/voice/) ---
    gnani_api_key: str = ""
    gnani_base_url: str = "https://api.vachana.ai"
    gnani_ws_url: str = "wss://api.vachana.ai"
    gnani_stt_model: str = "prisma-v3.0"
    # "indic-auto" = let Prisma v3.0 detect which of the 10 languages was spoken.
    gnani_stt_language: str = "indic-auto"
    # "transcribe" keeps English words in Latin script and returns DIGITS,
    # which is what makes "do kilo" arrive as "2" for the cart.
    gnani_stt_format: str = "transcribe"
    gnani_tts_model: str = "timbre-v3.0"
    gnani_tts_voice: str = "Shivani"
    gnani_tts_fallback_model: str = "timbre-v2.5"
    gnani_tts_sample_rate: int = 24000
    gnani_timeout_seconds: float = 20.0
    gnani_max_retries: int = 2
    gnani_circuit_breaker_failure_threshold: int = 3
    gnani_circuit_breaker_cooldown_seconds: float = 30.0
    # Below this many meaningful characters a transcript is treated as
    # "didn't catch that" (VoiceConfidenceRule) — never acted on.
    voice_min_transcript_chars: int = 2
    # Paise per second of audio, for the cost column on voice audit events.
    # Default 0: set it to your plan's rate and every event is priced.
    gnani_cost_paise_per_audio_second: float = 0.0
    gnani_cost_paise_per_tts_char: float = 0.0

    # --- Payments: Wallet + Cash on Delivery (see app/payments/) ---
    currency: str = "INR"
    # Demo wallet balance every new buyer starts with. Clearly labelled as
    # demo money everywhere it is shown.
    wallet_starting_balance_paise: int = 200_000  # ₹2,000
    wallet_max_topup_paise: int = 500_000  # ₹5,000 per top-up
    # Mode B (agent autopay) default limit, used when a buyer turns autopay
    # on without choosing a limit. Autopay is OFF for every agent by default.
    agent_autopay_default_limit_paise: int = 50_000  # ₹500

    # --- Rate limiting (requests per minute, per principal) ---
    rate_limit_chat_per_minute: int = 30
    rate_limit_voice_per_minute: int = 20

    # Account-wide cap across ALL of a buyer's agents together
    # (AccountSpendLimitRule) — closes the gap where three agents at ₹500 each
    # are ₹1,500 of exposure no single-credential rule sees.
    policy_account_agent_spend_cap_paise: int = 300_000  # ₹3,000

    # Policy thresholds. All in paise; all overridable via env, all with a
    # sane default so the system is never unbounded even if unconfigured.
    policy_default_spend_cap_paise: int = 500_000  # ₹5,000 — used only when a session sets no budget_paise
    policy_per_item_max_paise: int = 300_000  # ₹3,000 — no single catalog item is denied by default
    policy_quantity_max: int = 10
    policy_confirmation_threshold_paise: int = 100_000  # ₹1,000

    # --- the agent-readable catalog: agent-readable catalog ---
    merchant_display_name: str = "Gnani Shop"

    # --- the agent-readable catalog: bounded upsell ---
    policy_upsell_max_per_session: int = 1  # how many upsell offers this session will ever see, regardless of outcome
    policy_upsell_max_pct_of_cart: float = 0.50  # an offer priced above this fraction of the original cart value is blocked

    # --- campaigns: campaign orchestrator ---
    # Segmentation thresholds (deterministic, no LLM — app/campaigns/segmentation.py)
    campaign_lapsed_days: int = 90
    campaign_repeat_min_orders: int = 3
    campaign_high_value_threshold_paise: int = 200_000  # ₹2,000 lifetime spend
    campaign_category_loyal_min_share: float = 0.6

    # Offer policy — merchant-wide constants, never overridable by a campaign proposal
    campaign_max_discount_pct: float = 0.30  # ₹ off must never exceed 30% of list price
    campaign_min_margin_pct: float = 0.15  # discounted price must clear cost by at least 15%

    # Per-campaign-run parameters, resolved once from config before any offer is evaluated
    campaign_default_budget_paise: int = 300_000  # ₹3,000 max total giveaway per campaign
    campaign_min_segment_size: int = 5  # refuse to run a campaign on a smaller segment
    campaign_max_offers_per_window: int = 1  # a customer may be targeted this many times per window
    campaign_offer_frequency_window_days: int = 30

    # Control group + simulated redemption (see docs/ARCHITECTURE.md — this
    # whole block is a documented, explicit toy assumption, never observed data)
    campaign_control_group_fraction: float = 0.25
    campaign_base_organic_conversion_rate: float = 0.05  # baseline chance ANY customer buys the featured product anyway
    campaign_discount_lift_sensitivity: float = 0.6  # extra conversion-probability points per 1.0 (100%) of discount_pct

    # --- browse abandonment: browse abandonment segment ---
    campaign_browse_min_views: int = 3  # same SKU viewed at least this many times...
    campaign_browse_window_days: int = 7  # ...within this many days, with no purchase of it
    # Deliberately small: a nudge for someone already close to buying, not
    # persuasion for someone who needs convincing. Fixed by config, never
    # proposed by the LLM — there's no judgment call to make about "how much
    # to discount a product this customer already told us they're circling."
    campaign_browse_abandonment_discount_pct: float = 0.02

    # --- resilience: chaos injection + resilience ---
    # A global, sticky fault for a demo segment (e.g. CHAOS_FAULT=SLOW_LLM).
    # Empty = off. Overridable per-request via the X-Chaos-Fault header.
    # Both are gated by app_env == "development" in app/testing/chaos.py —
    # there is no way to enable chaos from a production config.
    chaos_fault: str = ""
    llm_circuit_breaker_failure_threshold: int = 3
    llm_circuit_breaker_cooldown_seconds: float = 30.0

    # --- the demand loop: demand-signal loop ---
    # Shared by every "N+ distinct buyers/sessions" notification (unmet
    # demand, browse abandonment, out-of-stock demand, attribute gap) — one
    # mental model, one tested helper (app/demand/aggregation.py::
    # crosses_threshold). Percentage of *active buyers* (real BUYER-role
    # Users with at least one AgentSession), with an absolute floor so a
    # tiny active-buyer count near the start of a demo can never trigger a
    # notification off one or two people.
    demand_notification_threshold_pct: float = 0.20
    demand_notification_threshold_floor: int = 5

    # --- agent principals: principals (buyer/merchant Google OAuth, agent credentials) ---
    google_client_id: str = ""
    google_client_secret: str = ""
    # NOT read by app/auth/oauth_router.py — the actual redirect_uri sent to
    # Google is derived per-request from request.url_for(), specifically so
    # the OAuth flow works whether the backend is reached via localhost:8842
    # or 127.0.0.1:8842 (the SessionMiddleware cookie carrying the CSRF
    # state is host-scoped, so login and callback must share a host, but
    # that host doesn't have to be fixed in advance). Kept as a documentation
    # default: register THIS value, and any other host/port you'll actually
    # use, as separate "Authorized redirect URIs" on the Google OAuth
    # client — Google allows more than one. See docs/ARCHITECTURE.md.
    google_redirect_uri: str = "http://localhost:8842/api/auth/google/callback"
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 24 * 7  # 7 days — a demo session, not a production-grade lifetime
    # Comma-separated emails that get MERCHANT on first login; anyone else
    # who signs in becomes a BUYER. A real deployment would have an actual
    # admin flow instead of a config allowlist — see docs/ARCHITECTURE.md.
    merchant_emails: str = ""
    # The full list of tool names a newly-created agent may pick scopes
    # from — one source of truth shared by the frontend's scope checkboxes
    # and the credential-creation endpoint's validation.
    agent_available_scopes: str = (
        "search_products,get_product,present_product,add_to_cart,view_cart,remove_from_cart,"
        "initiate_payment,decline_upsell,report_content_gap"
    )

    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def merchant_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.merchant_emails.split(",") if e.strip()}

    @property
    def agent_available_scope_list(self) -> list[str]:
        return [s.strip() for s in self.agent_available_scopes.split(",") if s.strip()]


settings = Settings()
