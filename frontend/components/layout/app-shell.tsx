"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { authApi } from "@/lib/api/auth";
import { ApiError, subscribeLoading } from "@/lib/api/client";
import type { User } from "@/lib/api/types";
import { LoadingBar, PageLoader } from "@/components/ui/states";
import { RealtimeProvider } from "@/lib/realtime/RealtimeProvider";

const links = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/campaigns", label: "Campaigns" },
  { href: "/leads", label: "Leads" },
  { href: "/templates", label: "Templates" },
  { href: "/smtp", label: "SMTP" },
  { href: "/settings", label: "Settings" },
];

function MenuIcon() {
  return (
    <span className="flex flex-col gap-1.5" aria-hidden>
      <span className="block h-0.5 w-5 bg-ink" />
      <span className="block h-0.5 w-5 bg-ink" />
      <span className="block h-0.5 w-5 bg-ink" />
    </span>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [pending, setPending] = useState(0);

  useEffect(() => {
    return subscribeLoading(setPending);
  }, []);

  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 768px)").matches;
    setOpen(desktop);
  }, []);

  useEffect(() => {
    let active = true;
    async function boot() {
      try {
        const me = await authApi.me();
        if (active) setUser(me);
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          try {
            await authApi.refresh();
            const me = await authApi.me();
            if (active) setUser(me);
            return;
          } catch {
            router.replace("/login");
            return;
          }
        }
        if (active) setError("Unable to load your session.");
      } finally {
        if (active) setReady(true);
      }
    }
    void boot();
    return () => {
      active = false;
    };
  }, [router]);

  async function logout() {
    await authApi.logout();
    router.replace("/login");
  }

  function closeOnMobile() {
    if (window.matchMedia("(max-width: 767px)").matches) setOpen(false);
  }

  return (
    <div className="min-h-screen bg-surface-soft">
      <LoadingBar active={pending > 0} />
      {open ? (
        <button
          type="button"
          aria-label="Close menu"
          className="fixed inset-0 z-30 bg-ink/40 md:hidden"
          onClick={() => setOpen(false)}
        />
      ) : null}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-hairline bg-canvas transition-transform duration-200 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-16 items-center justify-between px-4">
          <Link href="/dashboard" className="text-base font-semibold text-ink" onClick={closeOnMobile}>
            Mindsoft Mail
          </Link>
          <button
            type="button"
            aria-label="Close sidebar"
            className="rounded-full px-2 py-1 text-lg leading-none text-body hover:bg-surface-strong"
            onClick={() => setOpen(false)}
          >
            ×
          </button>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {links.map((link) => {
            const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
            return (
              <Link
                key={link.href}
                href={link.href}
                onClick={closeOnMobile}
                className={`block rounded-xl px-3 py-2.5 text-sm font-medium ${
                  active ? "bg-surface-strong text-primary" : "text-body hover:bg-surface-soft hover:text-ink"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-hairline p-4">
          <p className="truncate text-sm text-muted">{user?.email}</p>
          <button type="button" onClick={logout} className="mt-2 text-sm font-semibold text-primary">
            Sign out
          </button>
        </div>
      </aside>
      <div className={`min-h-screen transition-[padding] duration-200 ${open ? "md:pl-64" : ""}`}>
        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-hairline bg-canvas px-4">
          <button
            type="button"
            className="inline-flex h-10 w-10 items-center justify-center rounded-full hover:bg-surface-strong"
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            onClick={() => setOpen((value) => !value)}
          >
            <MenuIcon />
          </button>
          {pending > 0 ? (
            <span className="inline-flex items-center gap-2 text-xs font-medium text-muted">
              <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
              Loading
            </span>
          ) : (
            <span className="text-sm text-muted">Mindsoft Mail</span>
          )}
        </header>
        <main className="mx-auto w-full max-w-6xl px-4 py-8">
          {error ? <p className="mb-4 text-danger">{error}</p> : null}
          {!ready ? (
            <PageLoader label="Checking your session" />
          ) : (
            <RealtimeProvider enabled={Boolean(user)}>{children}</RealtimeProvider>
          )}
        </main>
      </div>
    </div>
  );
}
