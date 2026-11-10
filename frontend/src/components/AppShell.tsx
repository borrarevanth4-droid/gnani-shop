"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Languages, LogOut, Mic, Wallet } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { LANGUAGES, useI18n } from "@/lib/i18n";
import { fetchWallet } from "@/lib/api";

type NavKey = "shop" | "dashboard" | "orders" | "agent" | "wallet" | "voiceLab";

interface NavItem {
  key: NavKey | null;
  label: string;
  href: string;
  match?: (pathname: string) => boolean;
}

const BUYER_NAV: NavItem[] = [
  { key: "shop", label: "Shop", href: "/", match: (p) => p === "/" },
  { key: "dashboard", label: "Dashboard", href: "/dashboard" },
  { key: "orders", label: "Orders", href: "/orders" },
  { key: "wallet", label: "Wallet", href: "/wallet" },
  { key: "agent", label: "My Agent", href: "/agents" },
  { key: "voiceLab", label: "Voice Lab", href: "/voice-lab" },
];

const MERCHANT_NAV: NavItem[] = [
  { key: "dashboard", label: "Dashboard", href: "/merchant", match: (p) => p === "/merchant" },
  { key: null, label: "Voice", href: "/merchant/voice" },
  { key: "orders", label: "Orders", href: "/merchant/orders" },
  { key: null, label: "Products", href: "/merchant/products" },
  { key: null, label: "Campaigns", href: "/campaigns" },
  { key: null, label: "Audit", href: "/audit" },
  { key: "voiceLab", label: "Voice Lab", href: "/voice-lab" },
];

function NavLink({ item, pathname, label }: { item: NavItem; pathname: string; label: string }) {
  const active = item.match ? item.match(pathname) : pathname === item.href || pathname.startsWith(item.href + "/");
  return (
    <Link
      href={item.href}
      className={`relative inline-flex h-12 shrink-0 items-center px-3 text-[15px] font-medium tracking-[0.4px] transition-colors ${
        active ? "text-white" : "text-on-night-faint hover:text-white"
      }`}
    >
      {label}
      {active && <span className="absolute inset-x-3 bottom-0 h-[3px] rounded-full bg-accent" />}
    </Link>
  );
}

export function Wordmark({ dark = false }: { dark?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent text-white">
        <Mic size={15} />
      </span>
      <span className={`font-[family-name:var(--font-display)] text-lg font-light tracking-[0.2px] ${dark ? "text-white" : "text-ink"}`}>
        Gnani <span className="font-normal">Shop</span>
      </span>
    </span>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const { t, lang, setLang } = useI18n();
  const pathname = usePathname();
  const [balance, setBalance] = useState<number | null>(null);

  const nav = user?.type === "merchant" ? MERCHANT_NAV : user?.type === "buyer" ? BUYER_NAV : [];
  const homeHref = user?.type === "merchant" ? "/merchant" : "/";

  useEffect(() => {
    if (user?.type !== "buyer") return;
    fetchWallet()
      .then((w) => setBalance(w.balance_paise))
      .catch(() => setBalance(null));
  }, [user, pathname]);

  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-30 bg-night text-on-night">
        <div className="mx-auto flex h-14 max-w-[1280px] items-center justify-between gap-4 px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-4">
            <Link href={homeHref} className="shrink-0">
              <Wordmark dark />
            </Link>
            {nav.length > 0 && (
              <nav className="hidden items-center md:flex">
                {nav.map((item) => (
                  <NavLink key={item.href} item={item} pathname={pathname} label={item.key ? t(item.key) : item.label} />
                ))}
              </nav>
            )}
          </div>

          <div className="flex items-center gap-2 sm:gap-3">
            <label className="flex h-9 items-center gap-1.5 rounded-full border border-night-line px-3 text-xs text-on-night-soft">
              <Languages size={14} />
              <select
                aria-label="Language"
                value={lang}
                onChange={(e) => setLang(e.target.value)}
                className="bg-transparent text-xs text-white outline-none [&>option]:text-ink"
              >
                {LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.native}
                  </option>
                ))}
              </select>
            </label>
            {user?.type === "buyer" && balance != null && (
              <Link
                href="/wallet"
                className="hidden h-9 items-center gap-1.5 rounded-full bg-night-card px-3 font-mono text-xs tabular-nums text-white sm:inline-flex"
                title="Gnani Shop Wallet — demo money"
              >
                <Wallet size={13} /> ₹{(balance / 100).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
              </Link>
            )}
            {user && (
              <>
                <span className="hidden max-w-48 truncate text-sm text-on-night-faint lg:inline">{user.email}</span>
                <button
                  onClick={logout}
                  className="inline-flex h-9 items-center gap-1.5 rounded-full px-3 text-sm text-on-night-soft transition-colors hover:text-white"
                  title={t("signOut")}
                >
                  <LogOut size={14} />
                  <span className="hidden sm:inline">{t("signOut")}</span>
                </button>
              </>
            )}
          </div>
        </div>
        {nav.length > 0 && (
          <nav className="flex overflow-x-auto border-t border-night-line px-2 md:hidden">
            {nav.map((item) => (
              <NavLink key={item.href} item={item} pathname={pathname} label={item.key ? t(item.key) : item.label} />
            ))}
          </nav>
        )}
      </header>

      <main className="flex-1">{children}</main>

      <footer className="band-blue">
        <div className="mx-auto grid max-w-[1280px] gap-8 px-6 py-12 sm:grid-cols-[1fr_auto]">
          <div>
            <Wordmark dark />
            <p className="mt-3 max-w-md text-sm leading-relaxed text-white/80">
              A grocery store you can talk to, in 10 Indian languages. Speech by Gnani Vachana — Prisma v3.0 hears you, Timbre v3.0
              speaks back. The AI suggests, the rulebook decides, and only your tap moves money.
            </p>
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-white/90">
            {LANGUAGES.map((l) => (
              <span key={l.code}>{l.native}</span>
            ))}
          </div>
          <p className="text-xs text-white/70 sm:col-span-2">Built by Revanth · All money shown is demo money</p>
        </div>
      </footer>
    </div>
  );
}
