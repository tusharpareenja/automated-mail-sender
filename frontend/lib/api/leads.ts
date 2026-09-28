import { apiFetch, unwrap } from "@/lib/api/client";
import { env } from "@/lib/config/env";
import type { ImportResult, Lead, LeadFacets, LeadGroup } from "@/lib/api/types";

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : null;
}

export const leadsApi = {
  list: (q?: string) =>
    apiFetch<{ data: { items: Lead[]; next_cursor: string | null; has_more: boolean } }>(
      `/leads${q ? `?q=${encodeURIComponent(q)}` : ""}`,
    ).then(unwrap),
  inspect: (filename: string, csv_text: string) =>
    apiFetch<{
      data: {
        headers: string[];
        suggested_mapping: Record<string, string>;
        preview_rows: Array<Record<string, string>>;
        row_count: number;
      };
    }>("/leads/inspect", {
      method: "POST",
      body: JSON.stringify({ filename, csv_text, column_mapping: { Email: "email" } }),
    }).then(unwrap),
  import: (
    filename: string,
    csv_text: string,
    column_mapping: Record<string, string>,
    group_name: string,
  ) =>
    apiFetch<{ data: ImportResult }>("/leads/import", {
      method: "POST",
      body: JSON.stringify({ filename, csv_text, column_mapping, group_name }),
    }).then(unwrap),
  facets: () => apiFetch<{ data: LeadFacets }>("/leads/facets").then(unwrap),
  importWorkbook: async (file: File) => {
    const body = new FormData();
    body.append("file", file);
    const headers = new Headers();
    const csrf = readCookie("csrf_token");
    if (csrf) headers.set("X-CSRF-Token", csrf);
    const response = await fetch(`${env.apiBaseUrl}/leads/import-workbook`, {
      method: "POST",
      body,
      headers,
      credentials: "include",
    });
    const payload = await response.json();
    if (!response.ok) {
      const error = payload?.error;
      throw new Error(error?.message ?? "Workbook import failed");
    }
    return payload.data as {
      group_id: string;
      group_name: string;
      imported: number;
      updated: number;
      skipped_no_email: number;
    };
  },
  groups: () => apiFetch<{ data: LeadGroup[] }>("/leads/groups").then(unwrap),
  group: (id: string, q?: string, offset = 0) => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (offset) params.set("offset", String(offset));
    const suffix = params.toString() ? `?${params}` : "";
    return apiFetch<{ data: LeadGroup }>("/leads/groups/" + id + suffix).then(unwrap);
  },
  renameGroup: (id: string, name: string) =>
    apiFetch<{ data: LeadGroup }>("/leads/groups/" + id, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }).then(unwrap),
  deleteGroup: (id: string) =>
    apiFetch<{ data: { deleted: boolean } }>("/leads/groups/" + id, { method: "DELETE" }).then(unwrap),
  addLead: (
    groupId: string,
    lead: {
      email: string;
      first_name?: string;
      last_name?: string;
      company?: string;
      title?: string;
    },
  ) =>
    apiFetch<{ data: Lead }>("/leads/groups/" + groupId + "/leads", {
      method: "POST",
      body: JSON.stringify(lead),
    }).then(unwrap),
  removeLead: (groupId: string, leadId: string) =>
    apiFetch<{ data: { deleted: boolean } }>("/leads/groups/" + groupId + "/leads/" + leadId, {
      method: "DELETE",
    }).then(unwrap),
};
