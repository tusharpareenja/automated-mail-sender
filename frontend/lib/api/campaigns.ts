import { apiFetch, unwrap, type FetchOptions } from "@/lib/api/client";
import { env } from "@/lib/config/env";
import type { Campaign, CampaignAnalytics, CampaignEmail, CampaignPreview } from "@/lib/api/types";

export const campaignsApi = {
  list: () => apiFetch<{ data: Campaign[] }>("/campaigns").then(unwrap),
  get: (id: string, init?: FetchOptions) =>
    apiFetch<{ data: Campaign }>(`/campaigns/${id}`, init).then(unwrap),
  create: (body: Record<string, unknown>) =>
    apiFetch<{ data: Campaign }>("/campaigns", { method: "POST", body: JSON.stringify(body) }).then(unwrap),
  update: (id: string, body: Record<string, unknown>) =>
    apiFetch<{ data: Campaign }>(`/campaigns/${id}`, { method: "PATCH", body: JSON.stringify(body) }).then(unwrap),
  start: (id: string) =>
    apiFetch<{ data: Campaign }>(`/campaigns/${id}/start`, { method: "POST" }).then(unwrap),
  pause: (id: string) =>
    apiFetch<{ data: Campaign }>(`/campaigns/${id}/pause`, { method: "POST" }).then(unwrap),
  resume: (id: string) =>
    apiFetch<{ data: Campaign }>(`/campaigns/${id}/resume`, { method: "POST" }).then(unwrap),
  cancel: (id: string) =>
    apiFetch<{ data: Campaign }>(`/campaigns/${id}/cancel`, { method: "POST" }).then(unwrap),
  preview: (id: string) =>
    apiFetch<{ data: CampaignPreview[] }>(`/campaigns/${id}/preview`).then(unwrap),
  testEmail: (id: string, to_email: string) =>
    apiFetch(`/campaigns/${id}/test-email`, { method: "POST", body: JSON.stringify({ to_email }) }),
  emails: (id: string, init?: FetchOptions) =>
    apiFetch<{ data: CampaignEmail[] }>(`/campaigns/${id}/emails`, init).then(unwrap),
  trackingStatus: async () => {
    const response = await fetch(`${env.apiOrigin}/t/status`, { credentials: "include" });
    const body = (await response.json()) as { data: { public_url: string; is_local: boolean } };
    return body.data;
  },
  analytics: (id: string, init?: FetchOptions) =>
    apiFetch<{ data: CampaignAnalytics }>(`/campaigns/${id}/analytics`, init).then(unwrap),
};
