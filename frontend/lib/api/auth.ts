import { apiFetch, unwrap } from "@/lib/api/client";
import type { User } from "@/lib/api/types";

export const authApi = {
  register: (body: { email: string; password: string; full_name: string; company_name?: string }) =>
    apiFetch<{ data: User }>("/auth/register", { method: "POST", body: JSON.stringify(body) }).then(unwrap),
  login: (body: { email: string; password: string }) =>
    apiFetch<{ data: User }>("/auth/login", { method: "POST", body: JSON.stringify(body) }).then(unwrap),
  refresh: () => apiFetch<{ data: User }>("/auth/refresh", { method: "POST", silent: true, skipAuthRefresh: true }).then(unwrap),
  logout: () => apiFetch("/auth/logout", { method: "POST" }),
  me: () => apiFetch<{ data: User }>("/auth/me").then(unwrap),
  updateMe: (body: Partial<User>) =>
    apiFetch<{ data: User }>("/auth/me", { method: "PATCH", body: JSON.stringify(body) }).then(unwrap),
  forgotPassword: (email: string) =>
    apiFetch<{ data: { ok: boolean; reset_token?: string } }>("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),
  resetPassword: (token: string, password: string) =>
    apiFetch("/auth/reset-password", { method: "POST", body: JSON.stringify({ token, password }) }),
  wsTicket: () =>
    apiFetch<{ data: { token: string } }>("/auth/ws-ticket", { silent: true }).then(unwrap),
};
