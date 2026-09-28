import { apiFetch, unwrap } from "@/lib/api/client";
import type { SMTPAccount } from "@/lib/api/types";

export const smtpApi = {
  list: () => apiFetch<{ data: SMTPAccount[] }>("/smtp").then(unwrap),
  create: (body: Record<string, unknown>) =>
    apiFetch<{ data: SMTPAccount }>("/smtp", { method: "POST", body: JSON.stringify(body) }).then(unwrap),
  update: (id: string, body: Record<string, unknown>) =>
    apiFetch<{ data: SMTPAccount }>(`/smtp/${id}`, { method: "PATCH", body: JSON.stringify(body) }).then(unwrap),
  remove: (id: string) => apiFetch(`/smtp/${id}`, { method: "DELETE" }),
  test: (id: string) =>
    apiFetch<{ data: SMTPAccount }>(`/smtp/${id}/test`, { method: "POST" }).then(unwrap),
  sendTest: (id: string, to_email: string) =>
    apiFetch(`/smtp/${id}/send-test`, { method: "POST", body: JSON.stringify({ to_email }) }),
};
