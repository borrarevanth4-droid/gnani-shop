"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { LogIn, Mic, ShoppingBag, Store } from "lucide-react";
import { Wordmark } from "@/components/AppShell";
import { googleLoginUrl, setToken, useAuth } from "@/lib/auth";
import { demoLogin, fetchDemoLoginOptions } from "@/lib/api";
import type { DemoPrincipalOption } from "@/lib/types";
import { clearSessionId } from "@/lib/checkout";
import { Card, CardBody } from "@/components/ui/Card";

const ROLE_ICONS = {
  BUYER: ShoppingBag,
  MERCHANT: Store,
} as const;

function LoginInner() {
  const { user, loading } = useAuth();
  const searchParams = useSearchParams();
  const error = searchParams.get("error");

  const [demoPrincipals, setDemoPrincipals] = useState<DemoPrincipalOption[]>([]);
  const [pendingRole, setPendingRole] = useState<string | null>(null);
  const [demoError, setDemoError] = useState<string | null>(null);
  const [redirectTo, setRedirectTo] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && user) {
      window.location.href = "/";
    }
  }, [loading, user]);

  // A full navigation, not router.push — AuthProvider only fetches
  // /api/auth/me on mount, so this is what picks up the new token. Same
  // approach as the Google sign-in callback.
  useEffect(() => {
    if (redirectTo) window.location.href = redirectTo;
  }, [redirectTo]);

  useEffect(() => {
    let cancelled = false;
    fetchDemoLoginOptions()
      .then((options) => {
        if (!cancelled && options.available) setDemoPrincipals(options.principals);
      })
      // Not an error worth showing: outside development there are simply no
      // demo principals to offer, and Google sign-in above still works.
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleDemoLogin(role: "BUYER" | "MERCHANT") {
    setPendingRole(role);
    setDemoError(null);
    try {
      const result = await demoLogin(role);
      setToken(result.token);
      // Same reasoning as the Google callback: a chat session id left in
      // localStorage belongs to whoever last used this browser.
      clearSessionId();
      setRedirectTo("/");
    } catch (e) {
      setDemoError(e instanceof Error ? e.message : "Demo sign-in failed.");
      setPendingRole(null);
    }
  }

  if (!loading && user) {
    return null;
  }

  return (
    <div className="band-night-fade">
    <div className="mx-auto grid min-h-[80vh] w-full max-w-[1280px] items-center gap-12 px-6 py-16 md:grid-cols-[1.2fr_1fr]">
      <div className="hidden md:block">
        <span className="inline-flex items-center gap-2 rounded-full bg-accent px-3 py-1 text-xs font-medium text-white">
          <Mic size={13} /> Powered by Gnani Vachana
        </span>
        <h2 className="display mt-6 text-[44px] leading-tight text-white sm:text-[54px]">
          Shop by talking.
          <br />
          <span className="text-link-night">In your language.</span>
        </h2>
        <p className="mt-4 max-w-md text-[17px] leading-relaxed text-on-night-soft">
          Speak to Gnani Shop in any of 10 Indian languages. It understands, fills your cart, reads the total back to you — and never
          spends a rupee without your tap.
        </p>
        <div className="mt-5 flex max-w-md flex-wrap gap-1.5">
          {["हिन्दी", "English", "தமிழ்", "తెలుగు", "ಕನ್ನಡ", "മലയാളം", "मराठी", "বাংলা", "ગુજરાતી", "ਪੰਜਾਬੀ"].map((l) => (
            <span key={l} className="rounded-full bg-white/10 px-3 py-1.5 text-[13px] font-bold text-white">
              {l}
            </span>
          ))}
        </div>
      </div>
      <Card className="bg-white p-2">
        <CardBody className="flex flex-col items-center gap-4 text-center">
          <Wordmark />
          <h1 className="text-2xl font-semibold tracking-tight text-ink">Sign in</h1>
          <p className="text-sm text-ink-soft">
            Buyers and merchants both sign in with Google — the store assigns your role at first login. Software
            agents never sign in here; see <span className="font-medium text-ink">My Agent</span> once you&rsquo;re
            in.
          </p>
          {error && (
            <div className="w-full rounded-lg border border-danger/25 bg-danger-soft px-3 py-2 text-left text-sm text-danger">
              {error}
            </div>
          )}
          <a
            href={googleLoginUrl()}
            className="inline-flex h-12 w-full items-center justify-center gap-2.5 rounded-full bg-accent px-6 text-base font-bold text-white transition-colors duration-150 hover:bg-accent-hover"
          >
            <LogIn size={15} />
            Sign in with Google
          </a>

          {demoPrincipals.length > 0 && (
            <div className="mt-2 w-full border-t border-line pt-4 text-left">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium uppercase tracking-wide text-ink-soft">Or explore the demo</span>
                <span className="rounded-full border border-warning/30 bg-warning-soft px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-warning">
                  Dev only
                </span>
              </div>
              <p className="mt-1.5 text-xs leading-relaxed text-ink-soft">
                Pre-seeded accounts so you can look around without registering a Google OAuth client. Available only
                when the server runs with <code className="font-mono">APP_ENV=development</code> — the same gate that
                controls chaos injection.
              </p>
              {demoError && (
                <div className="mt-2 rounded-lg border border-danger/25 bg-danger-soft px-3 py-2 text-sm text-danger">
                  {demoError}
                </div>
              )}
              <div className="mt-3 flex flex-col gap-2">
                {demoPrincipals.map((principal) => {
                  const Icon = ROLE_ICONS[principal.role];
                  return (
                    <button
                      key={principal.role}
                      type="button"
                      onClick={() => handleDemoLogin(principal.role)}
                      disabled={pendingRole !== null}
                      className="flex w-full items-start gap-2.5 rounded-md border border-line-strong bg-surface px-3 py-2.5 text-left transition-colors duration-150 hover:bg-black/[0.02] focus-visible:outline-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <Icon size={15} className="mt-0.5 shrink-0 text-ink-soft" />
                      <span className="min-w-0">
                        <span className="block text-sm font-medium text-ink">
                          {pendingRole === principal.role ? "Signing in…" : `Continue as ${principal.name}`}
                        </span>
                        <span className="block text-xs leading-relaxed text-ink-soft">{principal.description}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto flex w-full max-w-sm flex-col gap-3 px-6 py-8">
          <div className="h-40 w-full animate-pulse rounded-lg bg-black/[0.05]" />
        </div>
      }
    >
      <LoginInner />
    </Suspense>
  );
}
