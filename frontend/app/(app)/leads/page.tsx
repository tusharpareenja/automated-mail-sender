"use client";

import { FormEvent, useEffect, useState } from "react";
import { leadsApi } from "@/lib/api/leads";
import { ApiError } from "@/lib/api/client";
import type { ImportResult, LeadGroup } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/field";
import { EmptyState, ErrorState, Notice, PageLoader } from "@/components/ui/states";

function nameFromFile(filename: string) {
  return filename.replace(/\.csv$/i, "").trim();
}

export default function LeadsPage() {
  const [groups, setGroups] = useState<LeadGroup[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [headers, setHeaders] = useState<string[]>([]);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [csvText, setCsvText] = useState("");
  const [filename, setFilename] = useState("");
  const [groupName, setGroupName] = useState("");
  const [rowCount, setRowCount] = useState(0);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [pageLoading, setPageLoading] = useState(true);
  const [rename, setRename] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newFirst, setNewFirst] = useState("");
  const [newCompany, setNewCompany] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [workbookLoading, setWorkbookLoading] = useState(false);
  const [leadSearch, setLeadSearch] = useState("");
  const [searching, setSearching] = useState(false);

  async function refresh() {
    setGroups(await leadsApi.groups());
  }

  useEffect(() => {
    let active = true;
    leadsApi
      .groups()
      .then((rows) => {
        if (active) setGroups(rows);
      })
      .catch(() => {
        if (active) setError("Unable to load lead groups.");
      })
      .finally(() => {
        if (active) setPageLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  async function onWorkbook(file: File) {
    setWorkbookLoading(true);
    setError("");
    try {
      const imported = await leadsApi.importWorkbook(file);
      setResult({
        id: imported.group_id,
        filename: file.name,
        status: "completed",
        total_rows: imported.imported + imported.updated + imported.skipped_no_email,
        valid_count: imported.imported + imported.updated,
        invalid_count: imported.skipped_no_email,
        duplicate_count: 0,
        column_mapping: {},
        error_report: [],
        group_name: imported.group_name,
      });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Workbook import failed.");
    } finally {
      setWorkbookLoading(false);
    }
  }

  async function onFile(file: File) {
    const text = await file.text();
    setCsvText(text);
    setFilename(file.name);
    setGroupName(nameFromFile(file.name));
    try {
      const inspected = await leadsApi.inspect(file.name, text);
      setHeaders(inspected.headers);
      setMapping(inspected.suggested_mapping);
      setRowCount(inspected.row_count);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to inspect CSV.");
    }
  }

  async function importCsv() {
    if (!groupName.trim()) {
      setError("Give this import a group name.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const imported = await leadsApi.import(filename, csvText, mapping, groupName.trim());
      setResult(imported);
      setHeaders([]);
      setFilename("");
      setGroupName("");
      setCsvText("");
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Import failed.");
    } finally {
      setLoading(false);
    }
  }

  async function loadMembers(groupId: string, q: string, offset = 0) {
    const detail = await leadsApi.group(groupId, q.trim(), offset);
    setGroups((current) =>
      current.map((item) => {
        if (item.id !== groupId) return item;
        if (offset === 0) return detail;
        const seen = new Set((item.leads ?? []).map((lead) => lead.id));
        return {
          ...detail,
          leads: [...(item.leads ?? []), ...(detail.leads ?? []).filter((lead) => !seen.has(lead.id))],
        };
      }),
    );
    return detail;
  }

  async function openGroup(group: LeadGroup) {
    if (openId === group.id) {
      setOpenId(null);
      return;
    }
    setError("");
    setLeadSearch("");
    try {
      const detail = await loadMembers(group.id, "");
      setOpenId(group.id);
      setRename(detail.name);
      setNewEmail("");
      setNewFirst("");
      setNewCompany("");
      setNewTitle("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to open this group.");
    }
  }

  async function searchMembers(event: FormEvent, groupId: string) {
    event.preventDefault();
    setSearching(true);
    setError("");
    try {
      await loadMembers(groupId, leadSearch);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Search failed.");
    } finally {
      setSearching(false);
    }
  }

  async function saveName(groupId: string) {
    setError("");
    try {
      const detail = await leadsApi.renameGroup(groupId, rename.trim());
      setGroups((current) => current.map((item) => (item.id === groupId ? { ...item, ...detail } : item)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to rename this group.");
    }
  }

  async function removeGroup(group: LeadGroup) {
    if (!confirm(`Delete the group “${group.name}”? Leads that are only in this group will be removed.`)) {
      return;
    }
    setError("");
    try {
      await leadsApi.deleteGroup(group.id);
      setGroups((current) => current.filter((item) => item.id !== group.id));
      if (openId === group.id) setOpenId(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to delete this group.");
    }
  }

  async function addLead(event: FormEvent, groupId: string) {
    event.preventDefault();
    setError("");
    try {
      await leadsApi.addLead(groupId, {
        email: newEmail.trim(),
        first_name: newFirst.trim(),
        company: newCompany.trim(),
        title: newTitle.trim(),
      });
      await loadMembers(groupId, leadSearch);
      setNewEmail("");
      setNewFirst("");
      setNewCompany("");
      setNewTitle("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to add this lead.");
    }
  }

  async function removeLead(groupId: string, leadId: string) {
    setError("");
    try {
      await leadsApi.removeLead(groupId, leadId);
      await loadMembers(groupId, leadSearch);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to remove this lead.");
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-normal tracking-tight">Leads</h1>
        <p className="mt-2 text-body">
          Each CSV becomes a group. Rename it, add a person, or pick the group when you start a campaign.
        </p>
      </div>
      {error ? <ErrorState message={error} /> : null}
      <section className="rounded-3xl border border-hairline bg-canvas p-6">
        <h2 className="text-lg font-normal">MindSurve workbook</h2>
        <p className="mt-1 text-sm text-body">
          Upload the research Excel file. Prospects become the MindSurve prospects group. Rows without an email are
          skipped. Needs review and Excluded have no email addresses, so they are not imported.
        </p>
        <input
          className="mt-3"
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          disabled={workbookLoading}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void onWorkbook(file);
            event.target.value = "";
          }}
        />
        {workbookLoading ? <p className="mt-2 text-sm text-muted">Importing workbook…</p> : null}
      </section>
      <section className="rounded-3xl border border-hairline bg-canvas p-6">
        <input
          type="file"
          accept=".csv,text/csv"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void onFile(file);
          }}
        />
        {filename ? (
          <p className="mt-3 text-sm text-body">
            {filename} · {rowCount} rows
          </p>
        ) : null}
        {headers.length > 0 ? (
          <div className="mt-4 space-y-3">
            <TextField
              label="Group name"
              value={groupName}
              onChange={(event) => setGroupName(event.target.value)}
            />
            {headers.map((header) => (
              <div key={header} className="grid gap-2 md:grid-cols-2">
                <span className="text-sm font-medium">{header}</span>
                <input
                  className="h-11 rounded-xl border border-hairline px-3"
                  value={mapping[header] ?? ""}
                  onChange={(event) => setMapping({ ...mapping, [header]: event.target.value })}
                />
              </div>
            ))}
            <Button type="button" loading={loading} onClick={importCsv}>
              Import as group
            </Button>
          </div>
        ) : null}
        {result ? (
          <Notice>
            Saved {result.valid_count} leads in “{result.group_name || "this group"}”. Invalid:{" "}
            {result.invalid_count}. Duplicates in the file: {result.duplicate_count}.
          </Notice>
        ) : null}
      </section>

      {pageLoading ? (
        <PageLoader label="Loading groups" />
      ) : groups.length === 0 ? (
        <EmptyState title="No groups yet" body="Upload a CSV and it will be saved as a named group." />
      ) : (
        <div className="space-y-4">
          {groups.map((group) => (
            <section key={group.id} className="rounded-3xl border border-hairline bg-canvas p-6">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <h2 className="text-xl font-normal">{group.name}</h2>
                  <p className="text-sm text-muted">
                    {group.lead_count} lead{group.lead_count === 1 ? "" : "s"}
                    {group.purpose && group.purpose !== "source" ? ` · ${group.purpose}` : ""}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button type="button" variant="secondary" onClick={() => openGroup(group)}>
                    {openId === group.id ? "Hide" : "Open"}
                  </Button>
                  <Button type="button" variant="danger" onClick={() => removeGroup(group)}>
                    Delete
                  </Button>
                </div>
              </div>
              {openId === group.id ? (
                <div className="mt-5 space-y-4">
                  <div className="flex flex-col gap-2 md:flex-row">
                    <input
                      className="h-11 flex-1 rounded-xl border border-hairline px-3"
                      value={rename}
                      onChange={(event) => setRename(event.target.value)}
                    />
                    <Button type="button" variant="secondary" onClick={() => saveName(group.id)}>
                      Rename
                    </Button>
                  </div>
                  <form className="grid gap-3 md:grid-cols-5" onSubmit={(event) => addLead(event, group.id)}>
                    <input
                      required
                      placeholder="Email"
                      className="h-11 rounded-xl border border-hairline px-3 md:col-span-2"
                      value={newEmail}
                      onChange={(event) => setNewEmail(event.target.value)}
                    />
                    <input
                      placeholder="First name"
                      className="h-11 rounded-xl border border-hairline px-3"
                      value={newFirst}
                      onChange={(event) => setNewFirst(event.target.value)}
                    />
                    <input
                      placeholder="Company"
                      className="h-11 rounded-xl border border-hairline px-3"
                      value={newCompany}
                      onChange={(event) => setNewCompany(event.target.value)}
                    />
                    <input
                      placeholder="Title"
                      className="h-11 rounded-xl border border-hairline px-3"
                      value={newTitle}
                      onChange={(event) => setNewTitle(event.target.value)}
                    />
                    <Button type="submit" className="md:col-span-5 md:w-fit">
                      Add lead
                    </Button>
                  </form>
                  <form className="flex flex-col gap-2 md:flex-row" onSubmit={(event) => searchMembers(event, group.id)}>
                    <input
                      placeholder="Search email, name, company, country, phone"
                      className="h-11 flex-1 rounded-xl border border-hairline px-3"
                      value={leadSearch}
                      onChange={(event) => setLeadSearch(event.target.value)}
                    />
                    <Button type="submit" variant="secondary" loading={searching}>
                      Search
                    </Button>
                  </form>
                  <p className="text-sm text-muted">
                    Showing {group.leads?.length ?? 0} of {group.match_count ?? group.lead_count}
                    {leadSearch.trim() ? " matches" : ` in this group (${group.lead_count} total)`}.
                  </p>
                  <div className="overflow-x-auto rounded-2xl border border-hairline">
                    <table className="min-w-[1100px] w-full text-left text-sm">
                      <thead className="border-b border-hairline text-xs text-muted">
                        <tr>
                          {[
                            "Email",
                            "Name",
                            "Title",
                            "Company",
                            "Country",
                            "Website",
                            "Study",
                            "Mail",
                            "Role",
                            "Phone",
                            "LinkedIn",
                            "",
                          ].map((heading) => (
                            <th key={heading || "actions"} className="px-3 py-2 font-medium">
                              {heading}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {(group.leads ?? []).length === 0 ? (
                          <tr>
                            <td colSpan={12} className="px-3 py-3 text-muted">
                              No leads match this search.
                            </td>
                          </tr>
                        ) : (
                          (group.leads ?? []).map((lead) => {
                            const extra = lead.custom_fields ?? {};
                            const name = [lead.first_name, lead.last_name].filter(Boolean).join(" ");
                            return (
                              <tr key={lead.id} className="border-b border-hairline align-top last:border-0">
                                <td className="px-3 py-2 font-medium">{lead.email}</td>
                                <td className="px-3 py-2">{name || "—"}</td>
                                <td className="px-3 py-2">{lead.title || "—"}</td>
                                <td className="max-w-[220px] px-3 py-2">
                                  {lead.company || "—"}
                                  {extra.initiative ? (
                                    <p className="mt-1 line-clamp-2 text-xs text-muted">{extra.initiative}</p>
                                  ) : null}
                                </td>
                                <td className="px-3 py-2">{lead.country || "—"}</td>
                                <td className="max-w-[160px] truncate px-3 py-2">{lead.website || extra.domain || "—"}</td>
                                <td className="px-3 py-2">{lead.study_opportunity || lead.industry || "—"}</td>
                                <td className="px-3 py-2">{lead.email_kind || "—"}</td>
                                <td className="px-3 py-2">{lead.role_verified ? "Verified" : "Unverified"}</td>
                                <td className="px-3 py-2">{extra.phone || "—"}</td>
                                <td className="max-w-[140px] truncate px-3 py-2">
                                  {extra.linkedin ? (
                                    <a href={extra.linkedin} className="underline" target="_blank" rel="noreferrer">
                                      Profile
                                    </a>
                                  ) : (
                                    "—"
                                  )}
                                </td>
                                <td className="px-3 py-2">
                                  <button type="button" className="text-xs underline" onClick={() => removeLead(group.id, lead.id)}>
                                    Remove
                                  </button>
                                </td>
                              </tr>
                            );
                          })
                        )}
                      </tbody>
                    </table>
                  </div>
                  {(group.leads?.length ?? 0) < (group.match_count ?? 0) ? (
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => loadMembers(group.id, leadSearch, group.leads?.length ?? 0)}
                    >
                      Load more
                    </Button>
                  ) : null}
                </div>
              ) : null}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
