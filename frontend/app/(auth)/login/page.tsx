"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { authApi } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { SignedOutOnly } from "@/components/auth/signed-out-only";
import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/field";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setLoading(true);
    setError("");
    try {
      await authApi.login({
        email: String(form.get("email")),
        password: String(form.get("password")),
      });
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to sign in.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <SignedOutOnly>
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4">
      <h1 className="text-3xl font-normal tracking-tight">Sign in</h1>
      <p className="mt-2 text-body">Use your workspace credentials.</p>
      <form onSubmit={onSubmit} className="mt-8 space-y-5">
        <TextField label="Email" name="email" type="email" required autoComplete="email" />
        <TextField label="Password" name="password" type="password" required autoComplete="current-password" />
        {error ? <p className="text-sm text-danger">{error}</p> : null}
        <Button type="submit" loading={loading} className="w-full">
          Sign in
        </Button>
      </form>
      <p className="mt-6 text-sm text-body">
        Need an account?{" "}
        <Link href="/register" className="font-semibold text-primary">
          Create one
        </Link>
      </p>
    </main>
    </SignedOutOnly>
  );
}
