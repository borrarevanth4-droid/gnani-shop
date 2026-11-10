"use client";

// Cart history: every past basket (one per order) with "Buy again", and a
// timeline of everything that went in or out of the cart — by your taps, by
// the voice/chat assistant, or by "Buy again".

import { useCallback, useEffect, useState } from "react";
import { History, Minus, Plus, RotateCcw, ShoppingBasket } from "lucide-react";
import { buyAgain, fetchCartHistory } from "@/lib/api";
import type { CartHistory } from "@/lib/types";
import RequireAuth from "@/components/RequireAuth";
import Button from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/Badge";
import EmptyState from "@/components/ui/EmptyState";
import { SkeletonRows } from "@/components/ui/Skeleton";

const rupees = (p: number) => `₹${(p / 100).toFixed(2)}`;
const when = (iso: string) => new Date(iso.endsWith("Z") ? iso : iso + "Z").toLocaleString();
const SOURCE: Record<string, string> = { you: "You", assistant: "Voice / chat assistant", reorder: "Buy again" };

function CartHistoryInner() {
  const [data, setData] = useState<CartHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"baskets" | "timeline">("baskets");
  const [busy, setBusy] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchCartHistory()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function again(orderId: number) {
    setBusy(orderId);
    setNotice(null);
    try {
      const r = await buyAgain(orderId);
      setNotice(
        `Added ${r.added.length} item${r.added.length === 1 ? "" : "s"} to your cart` +
          (r.skipped.length ? ` · not available now: ${r.skipped.join(", ")}` : "") +
          ". Go to Shop to check out."
      );
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-8 sm:px-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Cart history</h1>
        <p className="mt-1 text-sm text-ink-soft">
          Your past baskets and everything that went in or out of your cart — whether you tapped it or asked the voice
          assistant.
        </p>
      </header>

      <div className="flex gap-2">
        {(["baskets", "timeline"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-full px-4 py-1.5 text-[13px] font-semibold ${
              tab === t ? "bg-ink text-white" : "bg-black/[0.05] text-ink-soft hover:text-ink"
            }`}
          >
            {t === "baskets" ? "Past baskets" : "Cart timeline"}
          </button>
        ))}
      </div>

      {error && <div className="rounded-lg border border-danger/25 bg-danger-soft px-4 py-3 text-sm text-danger">{error}</div>}
      {notice && <div className="rounded-lg bg-black/[0.04] px-4 py-3 text-sm text-ink">{notice}</div>}

      {!data ? (
        <SkeletonRows count={5} />
      ) : tab === "baskets" ? (
        data.baskets.length === 0 ? (
          <EmptyState icon={ShoppingBasket} title="No past baskets yet" description="Each order you place shows up here." />
        ) : (
          <ul className="flex flex-col gap-4">
            {data.baskets.map((b) => (
              <li key={b.order_id} className="rounded-lg border border-line p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="font-semibold text-ink">
                      Order <span className="font-mono">#{b.order_id}</span> · {rupees(b.amount_paise)}
                    </p>
                    <p className="text-xs text-ink-faint">
                      {when(b.created_at)}
                      {b.payment_method ? ` · ${b.payment_method === "cod" ? "Cash on delivery" : "Wallet"}` : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <StatusBadge status={b.status} />
                    <Button size="sm" variant="primary" disabled={busy === b.order_id || !b.items.length} onClick={() => again(b.order_id)}>
                      <RotateCcw size={14} /> {busy === b.order_id ? "Adding…" : "Buy again"}
                    </Button>
                  </div>
                </div>
                <ul className="mt-3 divide-y divide-line text-sm">
                  {b.items.map((i) => (
                    <li key={i.sku} className="flex justify-between gap-4 py-1.5">
                      <span className="text-ink">
                        {i.quantity} × {i.name}
                      </span>
                      <span className="tabular-nums text-ink-soft">{rupees(i.unit_price_paise * i.quantity)}</span>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )
      ) : data.events.length === 0 ? (
        <EmptyState icon={History} title="Nothing yet" description="Add something to your cart and it shows up here." />
      ) : (
        <ol className="flex flex-col">
          {data.events.map((e) => (
            <li key={e.id} className="flex items-start gap-3 border-b border-line py-2.5 text-sm">
              <span
                className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${
                  e.action === "added" ? "bg-[#e3f6ea] text-[#1b7a43]" : "bg-danger-soft text-danger"
                }`}
              >
                {e.action === "added" ? <Plus size={14} /> : <Minus size={14} />}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-ink">
                  {e.action === "added" ? "Added" : "Removed"} {e.quantity} × {e.name}
                </p>
                <p className="text-xs text-ink-faint">
                  {when(e.created_at)} · by {SOURCE[e.source] ?? e.source} · cart #{e.cart_id}
                </p>
              </div>
              <span className="tabular-nums text-ink-soft">{rupees(e.unit_price_paise * e.quantity)}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export default function CartHistoryPage() {
  return (
    <RequireAuth allow={["buyer"]}>
      <CartHistoryInner />
    </RequireAuth>
  );
}
