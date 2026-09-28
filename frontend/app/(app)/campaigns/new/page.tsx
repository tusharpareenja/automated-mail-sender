"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { campaignsApi } from "@/lib/api/campaigns";
import { leadsApi } from "@/lib/api/leads";
import { smtpApi } from "@/lib/api/smtp";
import { templatesApi } from "@/lib/api/templates";
import { ApiError } from "@/lib/api/client";
import type { LeadFacets, LeadGroup, SMTPAccount, Template } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/field";
import { ErrorState, PageLoader } from "@/components/ui/states";

export default function NewCampaignPage() {
  const router = useRouter();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [groups, setGroups] = useState<LeadGroup[]>([]);
  const [accounts, setAccounts] = useState<SMTPAccount[]>([]);
  const [selectedGroups, setSelectedGroups] = useState<string[]>([]);
  const [selectedSmtp, setSelectedSmtp] = useState<string[]>([]);
  const [facets, setFacets] = useState<LeadFacets>({ countries: [], study_opportunities: [] });
  const [countries, setCountries] = useState<string[]>([]);
  const [studies, setStudies] = useState<string[]>([]);
  const [roleVerifiedOnly, setRoleVerifiedOnly] = useState(false);
  const [workEmailOnly, setWorkEmailOnly] = useState(false);
  const [error, setError] = useState("");
  const [groupError, setGroupError] = useState("");
  const [smtpError, setSmtpError] = useState("");
  const [loading, setLoading] = useState(false);
  const groupsRef = useRef<HTMLFieldSetElement>(null);
  const smtpRef = useRef<HTMLFieldSetElement>(null);
  const [pageLoading, setPageLoading] = useState(true);

  useEffect(() => {
    Promise.all([templatesApi.list(), leadsApi.groups(), smtpApi.list(), leadsApi.facets()])
      .then(([t, g, s, f]) => {
        setTemplates(t);
        setGroups(g);
        setAccounts(s);
        setFacets(f);
      })
      .catch(() => setError("Unable to load campaign setup data."))
      .finally(() => setPageLoading(false));
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const missingGroups = selectedGroups.length === 0;
    const missingSmtp = selectedSmtp.length === 0;
    setGroupError(missingGroups ? "Select at least one lead group." : "");
    setSmtpError(missingSmtp ? "Select at least one SMTP account." : "");
    if (missingGroups || missingSmtp) {
      setError(
        missingGroups && missingSmtp
          ? "Select a lead group and an SMTP account before saving."
          : missingGroups
            ? "Select at least one lead group."
            : "Select at least one SMTP account.",
      );
      (missingGroups ? groupsRef : smtpRef).current?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    setError("");
    setLoading(true);
    try {
      const campaign = await campaignsApi.create({
        name: String(form.get("name")),
        template_id: String(form.get("template_id")),
        group_ids: selectedGroups,
        countries,
        study_opportunities: studies,
        role_verified_only: roleVerifiedOnly,
        work_email_only: workEmailOnly,
        max_recipients: Number(form.get("max_recipients") || 150),
        smtp_account_ids: selectedSmtp,
        ai_enabled: true,
        hourly_limit: Number(form.get("hourly_limit") || 40),
        daily_limit: Number(form.get("daily_limit") || 300),
        delay_seconds: Number(form.get("delay_seconds") || 8),
      });
      router.push(`/campaigns/${campaign.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to create campaign.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-normal tracking-tight">New campaign</h1>
      {error ? <ErrorState message={error} /> : null}
      {pageLoading ? <PageLoader label="Loading campaign setup" /> : null}
      <form onSubmit={onSubmit} className="space-y-6 rounded-3xl border border-hairline bg-canvas p-6">
        <TextField label="Campaign name" name="name" required />
        <label className="block space-y-2">
          <span className="text-sm font-semibold">Template</span>
          <select name="template_id" required className="h-12 w-full rounded-xl border border-hairline px-3">
            <option value="">Select template</option>
            {templates.map((template) => (
              <option key={template.id} value={template.id}>
                {template.name}
              </option>
            ))}
          </select>
        </label>
        <fieldset ref={groupsRef}>
          <legend className="mb-2 text-sm font-semibold">Lead groups</legend>
          <div className="max-h-64 space-y-2 overflow-auto rounded-2xl border border-hairline p-3">
            {groups.length === 0 ? (
              <p className="text-sm text-muted">Import a CSV on the Leads page to create a group.</p>
            ) : (
              groups.map((group) => (
                <label key={group.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={selectedGroups.includes(group.id)}
                    onChange={(event) =>
                      setSelectedGroups((current) =>
                        event.target.checked
                          ? [...current, group.id]
                          : current.filter((id) => id !== group.id),
                      )
                    }
                  />
                  {group.name}{" "}
                  <span className="text-muted">
                    ({group.lead_count} lead{group.lead_count === 1 ? "" : "s"})
                  </span>
                </label>
              ))
            )}
          </div>
          <p className="mt-2 text-sm text-muted">
            People already sent from a source group are skipped. To follow up, select that campaign&apos;s Sent group.
            Failed sends land in a Failed group you can run again.
          </p>
          {groupError ? <p className="mt-2 text-sm text-danger">{groupError}</p> : null}
        </fieldset>
        <TextField label="Batch size" name="max_recipients" type="number" defaultValue="150" min={1} max={200} />
        {facets.countries.length > 0 ? (
          <fieldset>
            <legend className="mb-2 text-sm font-semibold">Countries</legend>
            <div className="flex flex-wrap gap-3">
              {facets.countries.map((country) => (
                <label key={country} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={countries.includes(country)}
                    onChange={(event) =>
                      setCountries((current) =>
                        event.target.checked ? [...current, country] : current.filter((item) => item !== country),
                      )
                    }
                  />
                  {country}
                </label>
              ))}
            </div>
            <p className="mt-2 text-sm text-muted">Leave every country unchecked to include all of them.</p>
          </fieldset>
        ) : null}
        {facets.study_opportunities.length > 0 ? (
          <fieldset>
            <legend className="mb-2 text-sm font-semibold">Study type</legend>
            <div className="flex flex-wrap gap-3">
              {facets.study_opportunities.map((study) => (
                <label key={study} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={studies.includes(study)}
                    onChange={(event) =>
                      setStudies((current) =>
                        event.target.checked ? [...current, study] : current.filter((item) => item !== study),
                      )
                    }
                  />
                  {study}
                </label>
              ))}
            </div>
          </fieldset>
        ) : null}
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={workEmailOnly}
            onChange={(event) => setWorkEmailOnly(event.target.checked)}
          />
          Work email only
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={roleVerifiedOnly}
            onChange={(event) => setRoleVerifiedOnly(event.target.checked)}
          />
          Verified role only
        </label>
        <fieldset ref={smtpRef}>
          <legend className="mb-2 text-sm font-semibold">SMTP accounts</legend>
          {accounts.length === 0 ? (
            <p className="text-sm text-muted">
              No sending account yet.{" "}
              <Link href="/smtp" className="font-semibold text-primary">
                Add an SMTP account
              </Link>
            </p>
          ) : null}
          {accounts.map((account) => (
            <label key={account.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={selectedSmtp.includes(account.id)}
                onChange={(event) =>
                  setSelectedSmtp((current) =>
                    event.target.checked ? [...current, account.id] : current.filter((id) => id !== account.id),
                  )
                }
              />
              {account.name} ({account.health_status})
            </label>
          ))}
          {smtpError ? <p className="mt-2 text-sm text-danger">{smtpError}</p> : null}
        </fieldset>
        <div className="grid gap-4 md:grid-cols-3">
          <TextField label="Hourly limit" name="hourly_limit" defaultValue="40" />
          <TextField label="Daily limit" name="daily_limit" defaultValue="300" />
          <TextField label="Delay seconds" name="delay_seconds" defaultValue="8" />
        </div>
        <Button type="submit" loading={loading}>
          Save draft
        </Button>
      </form>
    </div>
  );
}
