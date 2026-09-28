"use client";

import { FormEvent, useEffect, useState } from "react";
import { authApi } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import type { User } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { TextArea, TextField } from "@/components/ui/field";
import { ErrorState, Notice, PageLoader } from "@/components/ui/states";

export default function SettingsPage() {
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    authApi.me().then(setUser).catch(() => setError("Unable to load settings."));
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!user) return;
    const form = new FormData(event.currentTarget);
    setLoading(true);
    setError("");
    try {
      const updated = await authApi.updateMe({
        full_name: String(form.get("full_name")),
        company_name: String(form.get("company_name")),
        physical_address: String(form.get("physical_address")),
      });
      setUser(updated);
      setNotice("Profile updated.");
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to update settings.");
    } finally {
      setLoading(false);
    }
  }

  if (!user && !error) return <PageLoader label="Loading settings" />;

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-normal tracking-tight">Settings</h1>
      <p className="text-body">
        Add a company name and mailing address. These support responsible sending and unsubscribe identity.
      </p>
      {notice ? <Notice>{notice}</Notice> : null}
      {error ? <ErrorState message={error} /> : null}
      {user ? (
        <form onSubmit={onSubmit} className="max-w-xl space-y-4 rounded-3xl border border-hairline bg-canvas p-6">
          <TextField label="Full name" name="full_name" defaultValue={user.full_name} />
          <TextField label="Company" name="company_name" defaultValue={user.company_name ?? ""} />
          <TextArea label="Physical address" name="physical_address" defaultValue={user.physical_address ?? ""} />
          <Button type="submit" loading={loading}>
            {saved ? "Saved" : "Save settings"}
          </Button>
        </form>
      ) : null}
    </div>
  );
}
