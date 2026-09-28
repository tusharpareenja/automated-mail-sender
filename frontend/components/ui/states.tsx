"use client";

import { useEffect, useState } from "react";

export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-block h-5 w-5 animate-spin rounded-full border-2 border-current border-t-transparent ${className}`}
      aria-hidden
    />
  );
}

export function PageLoader({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 text-body">
      <Spinner className="h-8 w-8 text-primary" />
      <p className="text-sm font-medium">{label}…</p>
    </div>
  );
}

export function LoadingBar({ active }: { active: boolean }) {
  if (!active) return null;
  return (
    <div className="pointer-events-none fixed inset-x-0 top-0 z-50 h-0.5 overflow-hidden bg-transparent">
      <div className="h-full w-1/3 animate-[loading-slide_1.1s_ease-in-out_infinite] bg-primary" />
    </div>
  );
}

function FloatingToast({
  tone,
  children,
  onDismiss,
}: {
  tone: "error" | "success";
  children: React.ReactNode;
  onDismiss?: () => void;
}) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`fixed bottom-4 left-1/2 z-50 flex w-[min(32rem,calc(100%-2rem))] -translate-x-1/2 items-start gap-3 rounded-2xl px-4 py-3 text-sm shadow-lg ${
        tone === "error" ? "bg-danger text-white" : "bg-ink text-white"
      }`}
    >
      <p className="flex-1">{children}</p>
      {onDismiss ? (
        <button type="button" onClick={onDismiss} className="font-semibold text-white">
          Dismiss
        </button>
      ) : null}
    </div>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-3xl border border-hairline bg-canvas px-6 py-12 text-center">
      <h2 className="text-lg font-semibold text-ink">{title}</h2>
      <p className="mt-2 text-body">{body}</p>
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  const [open, setOpen] = useState(true);
  useEffect(() => {
    setOpen(true);
  }, [message]);
  return (
    <>
      {open ? (
        <FloatingToast tone="error" onDismiss={() => setOpen(false)}>
          {message}
        </FloatingToast>
      ) : null}
      <div className="rounded-2xl border border-danger/30 bg-canvas px-4 py-3 text-sm text-danger">
        {message}
      </div>
    </>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-2xl bg-surface-strong ${className}`} />;
}

export function Notice({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(true);
  useEffect(() => {
    setOpen(true);
    const timer = window.setTimeout(() => setOpen(false), 4000);
    return () => window.clearTimeout(timer);
  }, [children]);
  return (
    <>
      {open ? <FloatingToast tone="success">{children}</FloatingToast> : null}
      <div className="rounded-2xl border border-success/30 bg-canvas px-4 py-3 text-sm text-ink">
        {children}
      </div>
    </>
  );
}
