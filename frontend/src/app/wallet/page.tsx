"use client";

import { useEffect, useState } from "react";
import { Loader2, Plus, Wallet as WalletIcon } from "lucide-react";
import RequireAuth from "@/components/RequireAuth";
import Button from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { fetchWallet, topUpWallet } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Wallet } from "@/lib/types";

function rupees(paise: number): string {
  const sign = paise < 0 ? "−" : "";
  return `${sign}₹${(Math.abs(paise) / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const KIND_LABEL: Record<string, string> = {
  opening: "Starting balance",
  topup: "Top-up",
  debit: "Order payment",
  refund: "Refund",
};

export default function WalletPage() {
  return (
    <RequireAuth allow={["buyer"]}>
      <WalletView />
    </RequireAuth>
  );
}

function WalletView() {
  const { t } = useI18n();
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchWallet().then(setWallet).catch((e) => setError(e.message));
  }, []);

  async function topUp(amount: number) {
    setBusy(true);
    try {
      setWallet(await topUpWallet(amount));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-8 sm:px-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{t("wallet")}</h1>
        <p className="mt-1 text-sm text-ink-soft">
          Gnani Shop Wallet holds <span className="font-medium">demo money</span> — no bank or card is involved. Every entry below is a row
          in an append-only ledger; your balance is simply their sum, so it can never drift.
        </p>
      </header>

      {error && <p className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{error}</p>}

      <Card className="gnani-hero">
        <CardBody className="flex flex-wrap items-center justify-between gap-4 p-6">
          <div className="flex items-center gap-4">
            <span className="flex h-12 w-12 items-center justify-center rounded-full bg-accent-soft text-accent">
              <WalletIcon size={22} />
            </span>
            <div>
              <p className="text-xs uppercase tracking-wide text-ink-faint">
                {t("balance")} <Badge variant="voice" className="ml-1">{t("demoMoney")}</Badge>
              </p>
              <p className="font-mono text-3xl font-semibold tabular-nums text-ink">{wallet ? rupees(wallet.balance_paise) : "…"}</p>
            </div>
          </div>
          <div className="flex gap-2">
            {[50_000, 100_000, 200_000].map((amt) => (
              <Button key={amt} size="sm" onClick={() => topUp(amt)} disabled={busy}>
                {busy ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} {rupees(amt).replace(".00", "")}
              </Button>
            ))}
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Ledger</CardTitle>
          <CardDescription>A payment for an order can appear here only once — the database refuses a second debit for the same order.</CardDescription>
        </CardHeader>
        <CardBody className="p-0">
          <ul className="divide-y divide-line">
            {(wallet?.entries ?? []).map((e) => (
              <li key={e.id} className="flex items-center justify-between px-5 py-3 text-sm">
                <div>
                  <p className="text-ink">{KIND_LABEL[e.kind] ?? e.kind}{e.order_id ? ` · order #${e.order_id}` : ""}</p>
                  <p className="text-xs text-ink-faint">{new Date(e.created_at).toLocaleString()}</p>
                </div>
                <span className={`font-mono tabular-nums ${e.amount_paise < 0 ? "text-ink" : "text-success"}`}>{rupees(e.amount_paise)}</span>
              </li>
            ))}
          </ul>
        </CardBody>
      </Card>
    </div>
  );
}
