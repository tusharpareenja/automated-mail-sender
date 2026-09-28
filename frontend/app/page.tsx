import Link from "next/link";
import { SignedOutOnly } from "@/components/auth/signed-out-only";

export default function Home() {
  return (
    <SignedOutOnly>
    <div className="min-h-screen bg-canvas">
      <header className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
        <span className="font-semibold">Mindsoft Mail</span>
        <div className="flex gap-3">
          <Link href="/login" className="rounded-full bg-surface-strong px-5 py-2.5 text-sm font-semibold">
            Sign in
          </Link>
          <Link href="/register" className="rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-white">
            Create account
          </Link>
        </div>
      </header>
      <section className="bg-surface-dark px-4 py-20 text-white">
        <div className="mx-auto max-w-6xl">
          <p className="text-sm font-semibold uppercase tracking-wide text-muted-soft">Email campaigns</p>
          <h1 className="mt-4 max-w-3xl text-4xl font-normal tracking-tight md:text-6xl">
            Send personalized campaigns without losing control.
          </h1>
          <p className="mt-6 max-w-xl text-base text-muted-soft">
            Connect SMTP, import leads, preview AI personalization, and monitor delivery in one workspace.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/register" className="rounded-full bg-primary px-8 py-4 text-base font-semibold text-white">
              Get started
            </Link>
            <Link href="/login" className="rounded-full bg-surface-dark-elevated px-8 py-4 text-base font-semibold">
              Sign in
            </Link>
          </div>
        </div>
      </section>
    </div>
    </SignedOutOnly>
  );
}
