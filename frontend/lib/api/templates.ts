import { apiFetch, unwrap } from "@/lib/api/client";
import { env } from "@/lib/config/env";
import type { Template, TemplateAsset } from "@/lib/api/types";

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : null;
}

export const templatesApi = {
  list: () => apiFetch<{ data: Template[] }>("/templates").then(unwrap),
  get: (id: string) => apiFetch<{ data: Template }>(`/templates/${id}`).then(unwrap),
  create: (body: Record<string, unknown>) =>
    apiFetch<{ data: Template }>("/templates", { method: "POST", body: JSON.stringify(body) }).then(unwrap),
  update: (id: string, body: Record<string, unknown>) =>
    apiFetch<{ data: Template }>(`/templates/${id}`, { method: "PATCH", body: JSON.stringify(body) }).then(unwrap),
  duplicate: (id: string) =>
    apiFetch<{ data: Template }>(`/templates/${id}/duplicate`, { method: "POST" }).then(unwrap),
  remove: (id: string) => apiFetch(`/templates/${id}`, { method: "DELETE" }),
  preview: (id: string, body: Record<string, unknown>) =>
    apiFetch<{ data: { subject: string; html_body: string; text_body: string } }>(
      `/templates/${id}/preview`,
      { method: "POST", body: JSON.stringify(body) },
    ).then(unwrap),
  listAssets: (templateId: string) =>
    apiFetch<{ data: TemplateAsset[] }>(`/templates/${templateId}/assets`).then(unwrap),
  uploadAsset: async (templateId: string, file: File) => {
    const body = new FormData();
    body.append("file", file);
    const headers = new Headers();
    const csrf = readCookie("csrf_token");
    if (csrf) headers.set("X-CSRF-Token", csrf);
    const response = await fetch(`${env.apiBaseUrl}/templates/${templateId}/assets`, {
      method: "POST",
      body,
      headers,
      credentials: "include",
    });
    const payload = await response.json();
    if (!response.ok) {
      const error = payload?.error;
      throw new Error(error?.message ?? "Upload failed");
    }
    return payload.data as TemplateAsset;
  },
  deleteAsset: (assetId: string) =>
    apiFetch(`/templates/assets/${assetId}`, { method: "DELETE" }),
  assetContentUrl: (assetId: string) => `${env.apiBaseUrl}/media/assets/${assetId}`,
  /** Data URLs work inside srcDoc iframes; blob: URLs often do not. */
  fetchAssetDataUrl: async (assetId: string) => {
    const response = await fetch(`${env.apiBaseUrl}/media/assets/${assetId}`, {
      credentials: "include",
    });
    if (!response.ok) {
      throw new Error(`Unable to load asset preview (${response.status})`);
    }
    const blob = await response.blob();
    return await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(new Error("Failed to read asset"));
      reader.readAsDataURL(blob);
    });
  },
  fileToDataUrl: (file: File) =>
    new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(new Error("Failed to read file"));
      reader.readAsDataURL(file);
    }),
};
