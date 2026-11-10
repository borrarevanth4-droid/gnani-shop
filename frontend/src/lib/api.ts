import type {
  CartHistory,
  AgentChatResponse,
  AgentCreateRequest,
  AgentCreateResponse,
  AgentDetail,
  AgentSummary,
  AuditSessionSummary,
  AuditTrail,
  CampaignDetail,
  CampaignSummary,
  Cart,
  Category,
  ContentGap,
  ConversationDetail,
  ConversationSummary,
  DemoLoginOptions,
  DemoLoginResult,
  DashboardSummary,
  HeadlineNumbers,
  MeResponse,
  MerchantNotification,
  MerchantProductRow,
  OrderDetail,
  OrderListItem,
  PaymentInfo,
  PaymentResult,
  PendingApproval,
  Wallet,
  VoiceCatalog,
  VoiceTurn,
  LabResult,
  VoiceInsights,
  VoiceProfileInfo,
  CallBatch,
  ProductListResponse,
  RoleChoiceResult,
  Segment,
  SessionReplay,
} from "./types";
import { authHeaders } from "./auth";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? ""; // "" = same origin; Next forwards /api/* to the backend

const REQUEST_TIMEOUT_MS = 8000;
// The agent loop can make several sequential model calls (with retries/fallback)
// before responding — a plain product/cart request has no reason to take this long.
const AGENT_REQUEST_TIMEOUT_MS = 120_000;

export async function request<T>(path: string, init?: RequestInit, timeoutMs: number = REQUEST_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  // Sent on every request, not just the ones that strictly need it — public
  // endpoints (products, catalog feed) simply ignore it, and this keeps
  // every call site below from having to remember auth individually.
  const headers = { ...authHeaders(), ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers };

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers,
      signal: controller.signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new Error(`Timed out reaching the API at ${API_URL || "/api"}. Is the backend running?`);
    }
    throw new Error(`Could not reach the API at ${API_URL || "/api"}. Is the backend running?`);
  } finally {
    clearTimeout(timeout);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request to ${path} failed with ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export interface ProductQuery {
  category?: string | null;
  search?: string;
  minPricePaise?: number;
  maxPricePaise?: number;
  page?: number;
  pageSize?: number;
}

export function fetchProducts(query: ProductQuery = {}): Promise<ProductListResponse> {
  const params = new URLSearchParams();
  if (query.category) params.set("category", query.category);
  if (query.search) params.set("search", query.search);
  if (query.minPricePaise != null) params.set("min_price_paise", String(query.minPricePaise));
  if (query.maxPricePaise != null) params.set("max_price_paise", String(query.maxPricePaise));
  params.set("page", String(query.page ?? 1));
  params.set("page_size", String(query.pageSize ?? 50));
  return request<ProductListResponse>(`/api/products?${params.toString()}`);
}

export function fetchCategories(): Promise<Category[]> {
  return request<Category[]>("/api/categories");
}

export function fetchCart(): Promise<Cart> {
  return request<Cart>("/api/cart");
}

export function addCartItem(sku: string, quantity = 1): Promise<Cart> {
  return request<Cart>("/api/cart/items", {
    method: "POST",
    body: JSON.stringify({ sku, quantity }),
  });
}

export function removeCartItem(itemId: number): Promise<Cart> {
  return request<Cart>(`/api/cart/items/${itemId}`, { method: "DELETE" });
}

export function sendAgentMessage(
  sessionId: string,
  message: string,
  budgetPaise?: number | null,
  language?: string | null
): Promise<AgentChatResponse> {
  return request<AgentChatResponse>(
    "/api/agent/chat",
    {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, message, budget_paise: budgetPaise ?? null, language: language ?? null }),
    },
    AGENT_REQUEST_TIMEOUT_MS
  );
}

export function confirmPendingAction(sessionId: string, approve: boolean): Promise<AgentChatResponse> {
  return request<AgentChatResponse>(
    "/api/agent/confirm",
    { method: "POST", body: JSON.stringify({ session_id: sessionId, approve }) },
    AGENT_REQUEST_TIMEOUT_MS
  );
}

// Interactive chat scoped to one specific embedded agent credential — the
// credential's own spend_limit_paise/scopes are the only cap, no separate
// budget field. See app/auth/credentials_router.py's chat/confirm/quick-buy.
export function sendAgentCredentialMessage(
  credentialId: string,
  sessionId: string,
  message: string
): Promise<AgentChatResponse> {
  return request<AgentChatResponse>(
    `/api/agents/${credentialId}/chat`,
    { method: "POST", body: JSON.stringify({ session_id: sessionId, message }) },
    AGENT_REQUEST_TIMEOUT_MS
  );
}

export function confirmAgentCredentialAction(
  credentialId: string,
  sessionId: string,
  approve: boolean
): Promise<AgentChatResponse> {
  return request<AgentChatResponse>(
    `/api/agents/${credentialId}/confirm`,
    { method: "POST", body: JSON.stringify({ session_id: sessionId, approve }) },
    AGENT_REQUEST_TIMEOUT_MS
  );
}

// The product recommendation card's one-click "Confirm & Buy" — add to
// cart and start checkout in one call, fully policy-checked, no chat
// round-trip. Returns PaymentInfo so the Wallet / Cash on Delivery sheet opens immediately,
// or throws with the policy denial's own reason (e.g. out of scope, over
// the agent's spend limit).
export function quickBuy(
  credentialId: string,
  sessionId: string,
  sku: string,
  quantity: number = 1
): Promise<PaymentInfo> {
  return request<PaymentInfo>(
    `/api/agents/${credentialId}/quick-buy`,
    { method: "POST", body: JSON.stringify({ session_id: sessionId, sku, quantity }) },
    AGENT_REQUEST_TIMEOUT_MS
  );
}

export function fetchAuditTrail(sessionId: string): Promise<AuditTrail> {
  return request<AuditTrail>(`/api/audit/${sessionId}`);
}

export function fetchRecentAuditSessions(limit = 20): Promise<AuditSessionSummary[]> {
  return request<AuditSessionSummary[]>(`/api/audit/sessions?limit=${limit}`);
}

export function fetchSessionReplay(sessionId: string): Promise<SessionReplay> {
  return request<SessionReplay>(`/api/audit/${sessionId}/replay`);
}


export function logProductView(sku: string, sessionId: string | null): Promise<void> {
  // Fire-and-forget by contract: the backend endpoint is best-effort and
  // never errors, but a network failure (offline, blocked request) could
  // still reject the fetch — swallow it here too, since a page render or
  // a click must never wait on or break over a view-logging call.
  return request<void>(`/api/products/${encodeURIComponent(sku)}/view`, {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  }).catch(() => undefined);
}

export function fetchContentGaps(): Promise<ContentGap[]> {
  return request("/api/campaigns/content-gaps");
}

export function fetchSegments(): Promise<Segment[]> {
  return request<Segment[]>("/api/campaigns/segments");
}

export function fetchCampaigns(): Promise<CampaignSummary[]> {
  return request<CampaignSummary[]>("/api/campaigns");
}

export function fetchCampaign(campaignId: string): Promise<CampaignDetail> {
  return request<CampaignDetail>(`/api/campaigns/${campaignId}`);
}


export function fetchMe(): Promise<MeResponse> {
  return request<MeResponse>("/api/auth/me");
}

export function initiateCheckout(sessionId: string): Promise<PaymentInfo> {
  return request<PaymentInfo>("/api/checkout/initiate", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export function fetchCartHistory(): Promise<CartHistory> {
  return request<CartHistory>("/api/cart/history");
}

export function buyAgain(orderId: number): Promise<{ cart: Cart; added: string[]; skipped: string[] }> {
  return request(`/api/cart/reorder/${orderId}`, { method: "POST" });
}

export function fetchOrders(): Promise<OrderListItem[]> {
  return request<OrderListItem[]>("/api/orders");
}

export function fetchOrderDetail(orderId: number): Promise<OrderDetail> {
  return request<OrderDetail>(`/api/orders/${orderId}`);
}

export function fetchMerchantOrders(): Promise<OrderListItem[]> {
  return request<OrderListItem[]>("/api/merchant/orders");
}

export function fetchAgents(): Promise<AgentSummary[]> {
  return request<AgentSummary[]>("/api/agents");
}

export function fetchAgent(credentialId: string): Promise<AgentDetail> {
  return request<AgentDetail>(`/api/agents/${credentialId}`);
}

export function createAgent(payload: AgentCreateRequest): Promise<AgentCreateResponse> {
  return request<AgentCreateResponse>("/api/agents", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function revokeAgent(credentialId: string): Promise<AgentSummary> {
  return request<AgentSummary>(`/api/agents/${credentialId}/revoke`, { method: "POST" });
}

export function runAgent(
  credentialId: string,
  instruction?: string,
): Promise<{ reply: string; status: string; cart: Cart }> {
  return request(
    `/api/agents/${credentialId}/run`,
    { method: "POST", body: JSON.stringify({ instruction: instruction ?? null }) },
    AGENT_REQUEST_TIMEOUT_MS,
  );
}

// --- Dev-only role switch (backend/app/auth/role_router.py) ---

export function devSwitchRole(role: "BUYER" | "MERCHANT"): Promise<RoleChoiceResult> {
  return request<RoleChoiceResult>("/api/dev/switch-role", {
    method: "POST",
    body: JSON.stringify({ role }),
  });
}

// --- conversation history (scoped to one agent credential) ---

export function fetchAgentConversations(
  credentialId: string,
  includeArchived = false,
): Promise<ConversationSummary[]> {
  return request<ConversationSummary[]>(
    `/api/agents/${credentialId}/conversations?include_archived=${includeArchived}`,
  );
}

export function fetchAgentConversation(
  credentialId: string,
  sessionId: string,
): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/api/agents/${credentialId}/conversations/${sessionId}`);
}

export function archiveAgentConversation(
  credentialId: string,
  sessionId: string,
  archived = true,
): Promise<ConversationSummary> {
  return request<ConversationSummary>(
    `/api/agents/${credentialId}/conversations/${sessionId}/archive?archived=${archived}`,
    { method: "POST" },
  );
}

// --- Development-only demo sign-in (backend/app/testing/demo_login.py) ---
// `available` is false in every non-development environment, and the POST
// 404s there regardless of what this client sends.

export function fetchDemoLoginOptions(): Promise<DemoLoginOptions> {
  return request<DemoLoginOptions>("/api/auth/demo-login");
}

export function demoLogin(role: "BUYER" | "MERCHANT"): Promise<DemoLoginResult> {
  return request<DemoLoginResult>("/api/auth/demo-login", {
    method: "POST",
    body: JSON.stringify({ role }),
  });
}

// --- buyer dashboard ---

export function fetchDashboardSummary(): Promise<DashboardSummary> {
  return request<DashboardSummary>("/api/dashboard/summary");
}

// --- merchant dashboard ---

export function fetchMerchantNotifications(): Promise<MerchantNotification[]> {
  return request<MerchantNotification[]>("/api/merchant/notifications");
}

export function actOnNotification(
  id: number,
  status: "ACTED" | "DISMISSED"
): Promise<MerchantNotification> {
  return request<MerchantNotification>(`/api/merchant/notifications/${id}/action`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
}

export function fetchMerchantProducts(): Promise<MerchantProductRow[]> {
  return request<MerchantProductRow[]>("/api/merchant/products");
}

export function setProductPrice(sku: string, pricePaise: number): Promise<MerchantProductRow> {
  return request<MerchantProductRow>(`/api/merchant/products/${sku}/price`, {
    method: "POST",
    body: JSON.stringify({ price_paise: pricePaise }),
  });
}

export function setProductDiscount(sku: string, discountPct: number | null): Promise<MerchantProductRow> {
  return request<MerchantProductRow>(`/api/merchant/products/${sku}/discount`, {
    method: "POST",
    body: JSON.stringify({ discount_pct: discountPct }),
  });
}

export function toggleProductStock(sku: string): Promise<MerchantProductRow> {
  return request<MerchantProductRow>(`/api/merchant/products/${sku}/toggle-stock`, { method: "POST" });
}

export function fetchHeadlineNumbers(): Promise<HeadlineNumbers> {
  return request<HeadlineNumbers>("/api/merchant/headline");
}


// --- Payments: Gnani Shop Wallet + Cash on Delivery ---

export function payOrder(orderId: number, method: "wallet" | "cod"): Promise<PaymentResult> {
  return request<PaymentResult>("/api/payments/pay", {
    method: "POST",
    body: JSON.stringify({ order_id: orderId, method }),
  });
}

export function fetchWallet(): Promise<Wallet> {
  return request<Wallet>("/api/wallet");
}

export function topUpWallet(amountPaise: number): Promise<Wallet> {
  return request<Wallet>("/api/wallet/topup", {
    method: "POST",
    body: JSON.stringify({ amount_paise: amountPaise, request_key: crypto.randomUUID() }),
  });
}

// --- Agents: Mode B autopay + owner approvals ---

export function setAgentAutopay(credentialId: string, enabled: boolean, limitPaise?: number | null): Promise<AgentSummary> {
  return request<AgentSummary>(`/api/agents/${encodeURIComponent(credentialId)}/autopay`, {
    method: "POST",
    body: JSON.stringify({ enabled, limit_paise: limitPaise ?? null }),
  });
}

export function fetchAgentPending(credentialId: string): Promise<PendingApproval[]> {
  return request<PendingApproval[]>(`/api/agents/${encodeURIComponent(credentialId)}/pending`);
}

// --- Gnani voice ---

const VOICE_TIMEOUT_MS = 120_000;

async function multipart<T>(path: string, form: FormData, timeoutMs = VOICE_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_URL}${path}`, { method: "POST", body: form, headers: authHeaders(), signal: controller.signal });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(typeof body.detail === "string" ? body.detail : `Request to ${path} failed with ${res.status}`);
    }
    return (await res.json()) as T;
  } finally {
    clearTimeout(timeout);
  }
}

export function fetchVoiceCatalog(): Promise<VoiceCatalog> {
  return request<VoiceCatalog>("/api/voice/languages");
}

export function fetchVoiceStatus(): Promise<{ configured: boolean; stt_available: boolean; tts_available: boolean; stt_model: string; tts_model: string; default_voice: string }> {
  return request("/api/voice/status");
}

export function sendVoiceTurn(
  sessionId: string,
  wav: Blob,
  opts: { budgetPaise?: number | null; ttsModel?: string; languageHint?: string | null } = {}
): Promise<VoiceTurn> {
  const form = new FormData();
  form.append("audio", wav, "speech.wav");
  form.append("session_id", sessionId);
  if (opts.budgetPaise != null) form.append("budget_paise", String(opts.budgetPaise));
  if (opts.ttsModel) form.append("tts_model", opts.ttsModel);
  if (opts.languageHint) form.append("language_hint", opts.languageHint);
  return multipart<VoiceTurn>("/api/voice/turn", form);
}

export interface TtsOptions {
  text: string;
  voice?: string;
  model?: string;
  language?: string | null;
  speed?: number;
  sessionId?: string | null;
}

function ttsBody(o: TtsOptions): string {
  return JSON.stringify({
    text: o.text,
    voice: o.voice ?? null,
    model: o.model ?? null,
    language: o.language ?? null,
    speed: o.speed ?? 1.0,
    session_id: o.sessionId ?? null,
  });
}

/** Whole clip (WAV). */
export async function synthesize(o: TtsOptions): Promise<{ audio: Blob; latencyMs: number | null }> {
  const res = await fetch(`${API_URL}/api/voice/tts`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: ttsBody(o),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Speech failed (${res.status})`);
  }
  const latency = res.headers.get("X-Gnani-Latency-Ms");
  return { audio: await res.blob(), latencyMs: latency ? Number(latency) : null };
}

/** Streamed PCM chunks (NDJSON) — first audio plays while the rest is still being made. */
export async function synthesizeStream(
  o: TtsOptions,
  onChunk: (pcm: Uint8Array, sampleRate: number) => void
): Promise<{ firstChunkMs: number | null }> {
  const started = performance.now();
  const res = await fetch(`${API_URL}/api/voice/tts/stream`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: ttsBody(o),
  });
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Speech failed (${res.status})`);
  }
  const sampleRate = Number(res.headers.get("X-Sample-Rate") ?? "24000");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let firstChunkMs: number | null = null;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl: number;
    while ((nl = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (!line) continue;
      const msg = JSON.parse(line) as { audio?: string; final?: boolean; error?: string };
      if (msg.error) throw new Error(msg.error);
      if (msg.audio) {
        const bin = atob(msg.audio);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        if (bytes.length) {
          if (firstChunkMs === null) firstChunkMs = Math.round(performance.now() - started);
          onChunk(bytes, sampleRate);
        }
      }
    }
  }
  return { firstChunkMs };
}

export function labTranscribe(wav: Blob, formats: string[], compareKeyterms = true): Promise<{
  model: string;
  language_code: string;
  keyterm_count: number;
  results: LabResult[];
}> {
  const form = new FormData();
  form.append("audio", wav, "speech.wav");
  form.append("formats", formats.join(","));
  form.append("compare_keyterms", String(compareKeyterms));
  return multipart("/api/voice/lab/transcribe", form);
}

// --- Merchant voice features ---

export function fetchVoiceInsights(): Promise<VoiceInsights> {
  return request<VoiceInsights>("/api/merchant/voice/insights");
}

export function fetchVoiceProfile(): Promise<VoiceProfileInfo> {
  return request<VoiceProfileInfo>("/api/merchant/voice/profile");
}

export function createVoiceProfile(wav: Blob, displayName: string, consent: boolean): Promise<VoiceProfileInfo> {
  const form = new FormData();
  form.append("audio", wav, "reference.wav");
  form.append("display_name", displayName);
  form.append("consent", String(consent));
  return multipart<VoiceProfileInfo>("/api/merchant/voice/profile", form);
}

export async function previewVoiceProfile(text: string): Promise<Blob> {
  const res = await fetch(`${API_URL}/api/merchant/voice/profile/preview`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Preview failed (${res.status})`);
  }
  return res.blob();
}

export function deleteVoiceProfile(): Promise<{ deleted: boolean }> {
  return request("/api/merchant/voice/profile", { method: "DELETE" });
}

export function uploadCalls(files: File[]): Promise<CallBatch> {
  const form = new FormData();
  for (const f of files) form.append("files", f, f.name);
  return multipart<CallBatch>("/api/merchant/calls", form);
}

export function fetchCallBatches(): Promise<CallBatch[]> {
  return request<CallBatch[]>("/api/merchant/calls");
}

export function refreshCallBatch(id: number): Promise<CallBatch> {
  return request<CallBatch>(`/api/merchant/calls/${id}`, undefined, 60_000);
}

export function voiceStreamUrl(params: Record<string, string | null | undefined>): string {
  // WebSockets go straight to the backend (the dev proxy only forwards HTTP).
  const base = (process.env.NEXT_PUBLIC_WS_URL ?? (API_URL || `http://${window.location.hostname}:8842`)).replace(/^http/, "ws");
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) q.set(k, v);
  return `${base}/api/voice/stream?${q.toString()}`;
}
