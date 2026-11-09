"use client";

// The human tap that moves money (Mode A). Opens on an order that is
// AWAITING_PAYMENT and offers exactly two ways to finish it: the Gnani Shop
// Wallet (demo money) or Cash on Delivery. Nothing here is reachable by
// voice — it is always a tap.

import { useEffect, useState } from "react";
import { Banknote, CheckCircle2, Loader2, Wallet as WalletIcon, XCircle } from "lucide-react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import { fetchWallet, payOrder, topUpWallet } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { PaymentInfo, PaymentResult } from "@/lib/types";

function rupees(paise: number): string {
  return `₹${(paise / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

interface Props {
  payment: PaymentInfo;
  onClose: () => void;
  onDone: (result: PaymentResult) => void;
}

export default function PaymentSheet({ payment, onClose, onDone }: Props) {
  const { t } = useI18n();
  const [balance, setBalance] = useState<number | null>(payment.wallet_balance_paise ?? null);
  const [busy, setBusy] = useState<"wallet" | "cod" | "topup" | null>(null);
  const [result, setResult] = useState<PaymentResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchWallet()
      .then((w) => setBalance(w.balance_paise))
      .catch(() => {});
  }, []);

  async function pay(method: "wallet" | "cod") {
    setBusy(method);
    setError(null);
    try {
      const r = await payOrder(payment.order_id, method);
      setResult(r);
      if (r.wallet_balance_paise != null) setBalance(r.wallet_balance_paise);
      if (r.status === "PAID" || r.status === "CONFIRMED_COD") onDone(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function topUp() {
    setBusy("topup");
    try {
      const w = await topUpWallet(100_000);
      setBalance(w.balance_paise);
      setResult(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  const short = balance != null && balance < payment.amount_paise;
  const committed = result && (result.status === "PAID" || result.status === "CONFIRMED_COD");

  return (
    <Modal onClose={onClose} maxWidth="max-w-md">
      <div className="space-y-5">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">Order #{payment.order_id}</p>
          <p className="mt-1 font-mono text-3xl font-semibold tabular-nums text-ink">{rupees(payment.amount_paise)}</p>
          <p className="mt-1 text-sm text-ink-soft">{t("needsTap")} — nothing is charged until you choose below.</p>
        </div>

        {committed ? (
          <div className="flex items-start gap-3 rounded-md bg-success-soft p-4 text-success">
            <CheckCircle2 size={20} className="mt-0.5 shrink-0" />
            <div>
              <p className="font-medium">{result.status === "PAID" ? t("orderPlaced") : t("codPlaced")}</p>
              <p className="text-sm opacity-90">{result.message}</p>
            </div>
          </div>
        ) : (
          <>
            <button
              onClick={() => pay("wallet")}
              disabled={busy !== null || short}
              className="flex w-full items-center justify-between rounded-lg border border-line bg-surface p-4 text-left transition hover:border-accent hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-full bg-accent-soft text-accent">
                  {busy === "wallet" ? <Loader2 size={18} className="animate-spin" /> : <WalletIcon size={18} />}
                </span>
                <span>
                  <span className="block font-medium text-ink">{t("payWallet")}</span>
                  <span className="block text-xs text-ink-soft">
                    {t("balance")}: <span className="font-mono tabular-nums">{balance == null ? "…" : rupees(balance)}</span>{" "}
                    ({t("demoMoney")})
                  </span>
                </span>
              </span>
            </button>
            {short && (
              <div className="flex items-center justify-between rounded-md bg-warning-soft px-3 py-2 text-sm text-warning">
                <span>Not enough wallet balance.</span>
                <Button size="sm" variant="secondary" onClick={topUp} disabled={busy !== null}>
                  {busy === "topup" ? <Loader2 size={14} className="animate-spin" /> : null} Add ₹1,000 demo money
                </Button>
              </div>
            )}
            <button
              onClick={() => pay("cod")}
              disabled={busy !== null}
              className="flex w-full items-center justify-between rounded-lg border border-line bg-surface p-4 text-left transition hover:border-accent hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-full bg-voice-soft text-voice-deep">
                  {busy === "cod" ? <Loader2 size={18} className="animate-spin" /> : <Banknote size={18} />}
                </span>
                <span>
                  <span className="block font-medium text-ink">{t("payCod")}</span>
                  <span className="block text-xs text-ink-soft">Pay in cash when it arrives. No money moves now.</span>
                </span>
              </span>
            </button>
          </>
        )}

        {result && result.status === "FAILED" && (
          <div className="flex items-start gap-2 rounded-md bg-danger-soft p-3 text-sm text-danger">
            <XCircle size={16} className="mt-0.5 shrink-0" /> {result.message}
          </div>
        )}
        {error && <p className="rounded-md bg-danger-soft p-3 text-sm text-danger">{error}</p>}

        <div className="flex justify-end">
          <Button variant="ghost" onClick={onClose}>
            {committed ? "Done" : "Not now"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
