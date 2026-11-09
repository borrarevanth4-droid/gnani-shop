"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  AudioLines,
  Bot,
  FlaskConical,
  Languages,
  LayoutDashboard,
  LogOut,
  Megaphone,
  Mic,
  Package,
  Receipt,
  ScrollText,
  ShoppingBag,
  Wallet,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import { LANGUAGES, useI18n } from "@/lib/i18n";
import { fetchWallet } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";

type NavKey = "shop" | "dashboard" | "orders" | "agent" | "wallet" | "voiceLab";

interface NavItem {
  key: NavKey | null;
  label: string;
  href: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  match?: (pathname: string) => boolean;
}

const BUYER_NAV: NavItem[] = [
  { key: "shop", label: "Shop", href: "/", icon: ShoppingBag, match: (p) => p === "/" },
  { key: "dashboard", label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { key: "orders", label: "Orders", href: "/orders", icon: Receipt },
  { key: "wallet", label: "Wallet", href: "/wallet", icon: Wallet },
  { key: "agent", label: "My Agent", href: "/agents", icon: Bot },
  { key: "voiceLab", label: "Voice Lab", href: "/voice-lab", icon: FlaskConical },
];

const MERCHANT_NAV: NavItem[] = [
  { key: "dashboard", label: "Dashboard", href: "/merchant", icon: LayoutDashboard, match: (p) => p === "/merchant" },
  { key: null, label: "Voice", href: "/merchant/voice", icon: AudioLines },
  { key: "orders", label: "Orders", href: "/merchant/orders", icon: Receipt },
  { key: null, label: "Products", href: "/merchant/products", icon: Package },
  { key: null, label: "Campaigns", href: "/campaigns", icon: Megaphone },
  { key: null, label: "Audit", href: "/audit", icon: ScrollText },
  { key: "voiceLab", label: "Voice Lab", href: "/voice-lab", icon: FlaskConical },
];

function NavLink({ item, pathname, label }: { item: NavItem; pathname: string; label: string }) {
  const active = item.match ? item.match(pathname) : pathname === item.href || pathname.startsWith(item.href + "/");
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm font-medium transition-colors duration-150 ${
        active ? "bg-accent-soft text-accent" : "text-ink-soft hover:bg-black/[0.04] hover:text-ink"
      }`}
    >
      <Icon size={15} />
      {label}
    </Link>
  );
}

export function Wordmark() {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-voice text-white shadow-voice">
        <Mic size={15} />
      </span>
      <span className="text-[15px] font-semibold tracking-tight text-ink">
        Gnani <span className="text-voice-deep">Shop</span>
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
      <header className="sticky top-0 z-30 border-b border-line bg-surface/95 backdrop-blur-sm">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-5">
            <Link href={homeHref} className="shrink-0">
              <Wordmark />
            </Link>
            {nav.length > 0 && (
              <nav className="hidden items-center gap-1 overflow-x-auto md:flex">
                {nav.map((item) => (
                  <NavLink key={item.href} item={item} pathname={pathname} label={item.key ? t(item.key) : item.label} />
                ))}
              </nav>
            )}
          </div>

          <div className="flex items-center gap-2 sm:gap-3">
            <label className="flex items-center gap-1 rounded-md border border-line bg-surface px-1.5 py-1 text-xs text-ink-soft">
              <Languages size={14} />
              <select
                aria-label="Language"
                value={lang}
                onChange={(e) => setLang(e.target.value)}
                className="bg-transparent pr-1 text-xs text-ink outline-none"
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
                className="hidden items-center gap-1 rounded-md bg-accent-soft px-2 py-1 font-mono text-xs tabular-nums text-accent sm:inline-flex"
                title="Gnani Shop Wallet — demo money"
              >
                <Wallet size={13} /> ₹{(balance / 100).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
              </Link>
            )}
            {user && (
              <>
                <span className="hidden text-sm text-ink-soft lg:inline">{user.email}</span>
                {user.role && (
                  <Badge variant="neutral" className="hidden font-mono text-[10px] uppercase tracking-wide sm:inline-flex">
                    {user.role}
                  </Badge>
                )}
                <button
                  onClick={logout}
                  className="inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-ink-soft transition-colors duration-150 hover:bg-black/[0.04] hover:text-ink"
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
          <nav className="flex gap-1 overflow-x-auto border-t border-line px-3 py-1.5 md:hidden">
            {nav.map((item) => (
              <NavLink key={item.href} item={item} pathname={pathname} label={item.key ? t(item.key) : item.label} />
            ))}
          </nav>
        )}
      </header>

      <main className="flex-1">{children}</main>

      <footer className="border-t border-line bg-surface">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-1 px-6 py-4 text-xs text-ink-faint sm:flex-row">
          <span>Gnani Shop — voice commerce in 10 Indian languages · built by Revanth</span>
          <span>Speech by Gnani Vachana (Prisma v3.0 · Timbre v3.0) · all money shown is demo money</span>
        </div>
      </footer>
    </div>
  );
}
