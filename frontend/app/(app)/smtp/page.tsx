"use client";

import { FormEvent, useEffect, useState } from "react";
import { smtpApi } from "@/lib/api/smtp";
import { ApiError } from "@/lib/api/client";
import type { SMTPAccount } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/field";
import { EmptyState, ErrorState, Notice, PageLoader } from "@/components/ui/states";

const emptyForm = {
  name: "",
  host: "",
  port: "587",
  username: "",
  password: "",
  from_email: "",
  from_name: "",
  hourly_limit: "50",
  daily_limit: "400",
};

export default function SmtpPage() {
  const [accounts, setAccounts] = useState<SMTPAccount[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState(false);
  const [pageLoading, setPageLoading] = useState(true);
  const [testingId, setTestingId] = useState("");
  const [form, setForm] = useState(emptyForm);

  async function refresh() {
    try {
      setAccounts(await smtpApi.list());
    } catch {
      setError("Unable to load SMTP accounts.");
    }
  }

  useEffect(() => {
    let active = true;
    smtpApi
      .list()
      .then((rows) => {
        if (active) setAccounts(rows);
      })
      .catch(() => {
        if (active) setError("Unable to load SMTP accounts.");
      })
      .finally(() => {
        if (active) setPageLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      await smtpApi.create({
        ...form,
        port: Number(form.port),
        hourly_limit: Number(form.hourly_limit),
        daily_limit: Number(form.daily_limit),
        use_tls: true,
        use_ssl: false,
      });
      setForm(emptyForm);
      setNotice("SMTP account saved. The password is stored encrypted and will not be shown again.");
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to save SMTP account.");
    } finally {
      setLoading(false);
    }
  }

  async function test(id: string) {
    setTestingId(id);
    try {
      await smtpApi.test(id);
      setNotice("Connection test succeeded.");
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Connection test failed.");
    } finally {
      setTestingId("");
    }
  }

  async function remove(id: string) {
    if (!confirm("Delete this SMTP account? Campaigns using it will not be able to send.")) return;
    await smtpApi.remove(id);
    await refresh();
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-normal tracking-tight">SMTP accounts</h1>
        <p className="mt-2 text-body">Passwords are encrypted at rest and never returned after save.</p>
      </div>
      {notice ? <Notice>{notice}</Notice> : null}
      {error ? <ErrorState message={error} /> : null}
      <form onSubmit={onSubmit} className="grid gap-4 rounded-3xl border border-hairline bg-canvas p-6 md:grid-cols-2">
        <TextField label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
        <TextField label="Host" value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} required />
        <TextField label="Port" value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} required />
        <TextField label="Username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required />
        <TextField label="Password" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
        <TextField label="From email" type="email" value={form.from_email} onChange={(e) => setForm({ ...form, from_email: e.target.value })} required />
        <TextField label="From name" value={form.from_name} onChange={(e) => setForm({ ...form, from_name: e.target.value })} />
        <TextField label="Hourly limit" value={form.hourly_limit} onChange={(e) => setForm({ ...form, hourly_limit: e.target.value })} />
        <TextField label="Daily limit" value={form.daily_limit} onChange={(e) => setForm({ ...form, daily_limit: e.target.value })} />
        <div className="md:col-span-2">
          <Button type="submit" loading={loading}>
            {saved ? "Saved" : "Save account"}
          </Button>
        </div>
      </form>
      {pageLoading ? (
        <PageLoader label="Loading SMTP accounts" />
      ) : accounts.length === 0 ? (
        <EmptyState title="No sending accounts" body="Add an SMTP account before launching a campaign." />
      ) : (
        <div className="space-y-3">
          {accounts.map((account) => (
            <article key={account.id} className="rounded-3xl border border-hairline bg-canvas p-5">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <h2 className="font-semibold">{account.name}</h2>
                  <p className="text-sm text-body">
                    {account.host}:{account.port} · {account.from_email}
                  </p>
                  <p className="text-sm text-muted">
                    Health: {account.health_status} · {account.hourly_limit}/hr · {account.daily_limit}/day
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button variant="secondary" loading={testingId === account.id} onClick={() => test(account.id)}>
                    Test connection
                  </Button>
                  <Button variant="ghost" onClick={() => remove(account.id)}>
                    Delete
                  </Button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
