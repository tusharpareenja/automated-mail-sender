import { apiFetch, unwrap } from "@/lib/api/client";
import type { Dashboard } from "@/lib/api/types";

export const analyticsApi = {
  dashboard: () => apiFetch<{ data: Dashboard }>("/dashboard").then(unwrap),
  events: () =>
    apiFetch<{
      data: Array<{
        id: string;
        campaign_id: string;
        email_id: string;
        event_type: string;
        created_at: string;
      }>;
    }>("/events").then(unwrap),
};
