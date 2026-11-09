"use client";

// Mode A / Mode B for one agent, plus the owner's approval queue.
//
// Mode A (default): every payment this agent proposes waits here for the
// owner's decision. Mode B (opt-in): the agent may pay from the wallet on its
// own, but only up to its separate autopay limit — never Cash on Delivery.
// Only the owner, signed in, can switch it; an agent key can't reach this.

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Loader2, ShieldCheck, Zap } from "lucide-react";
import Button from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { confirmAgentCredentialAction, fetchAgentPending, setAgentAutopay } from "@/lib/api";
import type { AgentSummary, PaymentInfo, PendingApproval } from "@/lib/types";
import PaymentSheet from "@/components/PaymentSheet";

function rupees(paise: number): string {
  return `₹${(paise / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

export default function AgentAutopayPanel({ agent, onChanged }: { agent: AgentSummary; onChanged: () => void }) {
  const [limit, setLimit] = useState(String((agent.autopay_limit_paise || 50_000) / 100));
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<PendingApproval[]>([]);
  const [sheet, setSheet] = useState<PaymentInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadPending = useCallback(() => {
    if (agent.status !== "ACTIVE") return;
    fetchAgentPending(agent.id).then(setPending).catch(() => {});
  }, [agent.id, agent.status]);
  useEffect(loadPending, [loadPending]);

  async function save(enabled: boolean) {
    setBusy(true);
    setError(null);
    try {
      const paise = Math.round(Number(limit) * 100);
      await setAgentAutopay(agent.id, enabled, enabled && paise > 0 ? paise : null);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function decide(sessionId: string, approve: boolean) {
    setBusy(true);
    try {
      const r = await confirmAgentCredentialAction(agent.id, sessionId, approve);
      if (r.payment && r.payment.status === "AWAITING_PAYMENT") setSheet(r.payment);
      loadPending();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (agent.status !== "ACTIVE") return null;

  return (
    <div className="mt-3 grid gap-3 md:grid-cols-2">
      <div className={`rounded-lg border p-3 ${agent.autopay_enabled ? "border-voice/40 bg-voice-soft" : "border-line bg-black/[0.015]"}`}>
        <div className="flex items-center justify-between">
          <p className="flex items-center gap-1.5 text-sm font-medium text-ink">
            {agent.autopay_enabled ? <Zap size={14} className="text-voice-deep" /> : <ShieldCheck size={14} className="text-accent" />}
            {agent.autopay_enabled ? "Mode B · autopay on" : "Mode A · you approve every payment"}
          </p>
          <Badge variant={agent.autopay_enabled ? "voice" : "accent"}>{agent.autopay_enabled ? "optional" : "default"}</Badge>
        </div>
        <p className="mt-1 text-xs text-ink-soft">
          {agent.autopay_enabled
            ? `Pays from your wallet on its own up to ${rupees(agent.autopay_limit_paise)} (used ${rupees(agent.autopay_spent_paise)}). Wallet only — never Cash on Delivery. Anything above waits for you.`
            : "This agent can fill a cart and ask to pay, but money moves only after your tap."}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
          <label className="flex items-center gap-1 text-ink-soft">
            Autopay limit ₹
            <input value={limit} onChange={(e) => setLimit(e.target.value.replace(/[^0-9.]/g, ""))} className="w-20 rounded border border-line bg-surface px-1.5 py-1 font-mono" />
          </label>
          {agent.autopay_enabled ? (
            <>
              <Button size="sm" onClick={() => save(true)} disabled={busy}>
                Update limit
              </Button>
              <Button size="sm" variant="destructive" onClick={() => save(false)} disabled={busy}>
                Turn off autopay
              </Button>
            </>
          ) : (
            <Button size="sm" onClick={() => save(true)} disabled={busy}>
              {busy ? <Loader2 size={13} className="animate-spin" /> : <Zap size={13} />} Turn on autopay (Mode B)
            </Button>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-line p-3">
        <p className="text-sm font-medium text-ink">Waiting for your approval</p>
        {pending.length === 0 ? (
          <p className="mt-1 flex items-center gap-1.5 text-xs text-ink-faint">
            <CheckCircle2 size={13} /> Nothing pending.
          </p>
        ) : (
          <ul className="mt-2 space-y-2">
            {pending.map((p) => (
              <li key={p.session_id} className="rounded-md bg-warning-soft p-2 text-xs">
                <p className="font-medium text-warning">{p.tool_name === "initiate_payment" ? "Payment request" : p.tool_name}</p>
                <p className="mt-0.5 text-ink-soft">{p.reason}</p>
                <div className="mt-1.5 flex gap-1.5">
                  <Button size="sm" variant="primary" onClick={() => decide(p.session_id, true)} disabled={busy}>
                    Approve
                  </Button>
                  <Button size="sm" onClick={() => decide(p.session_id, false)} disabled={busy}>
                    Decline
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
      {error && <p className="rounded-md bg-danger-soft px-3 py-2 text-xs text-danger md:col-span-2">{error}</p>}
      {sheet && <PaymentSheet payment={sheet} onClose={() => setSheet(null)} onDone={() => onChanged()} />}
    </div>
  );
}
