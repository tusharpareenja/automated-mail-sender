"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { authApi } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { SignedOutOnly } from "@/components/auth/signed-out-only";
import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/field";

export default function RegisterPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password"));
    if (password.length < 10) {
      setError("Password must be at least 10 characters.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await authApi.register({
        email: String(form.get("email")),
        password,
        full_name: String(form.get("full_name")),
        company_name: String(form.get("company_name") || "") || undefined,
      });
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to create your account.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <SignedOutOnly>
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4 py-10">
      <h1 className="text-3xl font-normal tracking-tight">Create your workspace</h1>
      <p className="mt-2 text-body">You will be signed in immediately after registration.</p>
      <form onSubmit={onSubmit} className="mt-8 space-y-5">
        <TextField label="Full name" name="full_name" required autoComplete="name" />
        <TextField label="Work email" name="email" type="email" required autoComplete="email" />
        <TextField label="Company" name="company_name" autoComplete="organization" />
        <TextField
          label="Password"
          name="password"
          type="password"
          required
          minLength={10}
          hint="At least 10 characters."
          autoComplete="new-password"
        />
        {error ? <p className="text-sm text-danger">{error}</p> : null}
        <Button type="submit" loading={loading} className="w-full">
          Create account
        </Button>
      </form>
      <p className="mt-6 text-sm text-body">
        Already registered?{" "}
        <Link href="/login" className="font-semibold text-primary">
          Sign in
        </Link>
      </p>
    </main>
    </SignedOutOnly>
  );
}
