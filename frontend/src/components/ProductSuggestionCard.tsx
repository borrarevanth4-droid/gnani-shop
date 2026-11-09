"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { quickBuy } from "@/lib/api";
import type { PaymentInfo, ProductSuggestion } from "@/lib/types";
import PaymentSheet from "@/components/PaymentSheet";
import Button from "@/components/ui/Button";

interface Props {
  suggestion: ProductSuggestion;
  credentialId: string;
  sessionId: string;
  onSuccess: (message: string) => void;
  onFailure: (message: string) => void;
}

export default function ProductSuggestionCard({ suggestion, credentialId, sessionId, onSuccess, onFailure }: Props) {
  const [buying, setBuying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sheet, setSheet] = useState<PaymentInfo | null>(null);

  async function handleConfirm() {
    setBuying(true);
    setError(null);
    try {
      // The card click is the human confirmation; the order then waits for
      // the Wallet / Cash on Delivery tap in the PaymentSheet.
      const payment = await quickBuy(credentialId, sessionId, suggestion.sku, 1);
      if (payment.status === "PAID") {
        onSuccess(`Order #${payment.order_id} paid — ₹${(payment.amount_paise / 100).toFixed(2)} from the wallet (demo money).`);
      } else {
        setSheet(payment);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBuying(false);
    }
  }

  const withinBudget = suggestion.within_budget;
  const Icon = withinBudget ? CheckCircle2 : AlertTriangle;
  const toneClass = withinBudget ? "border-success/25 bg-success-soft" : "border-warning/25 bg-warning-soft";
  const iconClass = withinBudget ? "text-success" : "text-warning";
  const outOfStock = suggestion.stock === 0;

  return (
    <div className={`rounded-lg border p-3.5 text-sm ${toneClass}`}>
      <div className="flex items-start gap-2">
        <Icon size={16} className={`mt-0.5 shrink-0 ${iconClass}`} />
        <div className="min-w-0 flex-1">
          <p className="font-medium text-ink">{suggestion.name}</p>
          <p className="text-xs text-ink-soft">{suggestion.unit}</p>
          <p className="mt-1.5 font-mono text-base font-semibold tabular-nums text-ink">{suggestion.price_display}</p>
          <p className={`mt-1 ${iconClass}`}>{suggestion.note}</p>
          {outOfStock && <p className="mt-1 text-xs font-medium text-danger">Out of stock right now.</p>}
        </div>
      </div>

      {error && (
        <div className="mt-2.5 rounded-md border border-danger/25 bg-danger-soft px-2.5 py-1.5 text-xs text-danger">
          {error}
        </div>
      )}

      <Button variant="primary" size="sm" onClick={handleConfirm} disabled={buying || outOfStock} className="mt-3 w-full">
        {buying ? "…" : "Confirm & Buy"}
      </Button>
      {sheet && (
        <PaymentSheet
          payment={sheet}
          onClose={() => setSheet(null)}
          onDone={(r) => {
            if (r.status === "FAILED") onFailure(r.message);
            else onSuccess(r.message);
          }}
        />
      )}
    </div>
  );
}
