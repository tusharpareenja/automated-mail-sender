"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { analyticsApi } from "@/lib/api/analytics";
import type { Dashboard, LiveEvent } from "@/lib/api/types";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { useRealtimeEvents } from "@/lib/realtime/useRealtimeEvents";

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  const [live, setLive] = useState<LiveEvent[]>([]);

  useEffect(() => {
    analyticsApi
      .dashboard()
      .then(setData)
      .catch(() => setError("Unable to load dashboard. Please try again."));
  }, []);

  useRealtimeEvents((event) => {
    setLive((current) => [{ ...event, created_at: new Date().toISOString() }, ...current].slice(0, 12));
    setData((current) => {
      if (!current) return current;
      if (event.type === "EMAIL_OPENED") return { ...current, tracked_opens: current.tracked_opens + 1 };
      if (event.type === "LINK_CLICKED") return { ...current, clicks: current.clicks + 1 };
      if (event.type === "EMAIL_SENT") return { ...current, emails_sent: current.emails_sent + 1 };
      if (event.type === "EMAIL_FAILED") return { ...current, failures: current.failures + 1 };
      if (event.type === "EMAIL_BOUNCED") return { ...current, bounce_signals: current.bounce_signals + 1 };
      return current;
    });
  });

  if (error) return <ErrorState message={error} />;
  if (!data) {
    return (
      <div className="grid gap-4 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-28" />
        ))}
      </div>
    );
  }

  const cards = [
    ["Active campaigns", data.active_campaigns],
    ["Leads", data.total_leads],
    ["Emails sent", data.emails_sent],
    ["Tracked open signals", data.tracked_opens],
    ["Clicks", data.clicks],
    ["Failures", data.failures],
    ["Bounce signals", data.bounce_signals],
  ] as const;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-normal tracking-tight">Dashboard</h1>
        <p className="mt-2 text-body">A concise view of sending activity and campaign health.</p>
      </div>
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map(([label, value]) => (
          <article key={label} className="rounded-3xl border border-hairline bg-canvas p-6">
            <p className="text-sm text-muted">{label}</p>
            <p className="tabular mt-3 text-2xl text-ink">{value}</p>
          </article>
        ))}
      </section>
      <section>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Recent campaigns</h2>
          <Link href="/campaigns/new" className="text-sm font-semibold text-primary">
            New campaign
          </Link>
        </div>
        {data.recent_campaigns.length === 0 ? (
          <EmptyState title="No campaigns yet" body="Create a template, import leads, then launch your first campaign." />
        ) : (
          <div className="overflow-x-auto rounded-3xl border border-hairline bg-canvas">
            <table className="min-w-full text-left text-sm">
              <thead className="text-muted">
                <tr>
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Sent</th>
                  <th className="px-4 py-3">Opens</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_campaigns.map((campaign) => (
                  <tr key={campaign.id} className="border-t border-hairline">
                    <td className="px-4 py-3">
                      <Link href={`/campaigns/${campaign.id}`} className="font-medium text-primary">
                        {campaign.name}
                      </Link>
                    </td>
                    <td className="px-4 py-3">{campaign.status}</td>
                    <td className="tabular px-4 py-3">{campaign.sent_count}</td>
                    <td className="tabular px-4 py-3">{campaign.open_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="rounded-3xl border border-hairline bg-canvas p-6">
        <h2 className="text-lg font-semibold">Live activity</h2>
        {live.length === 0 ? (
          <p className="mt-2 text-sm text-muted">
            Open signals and link clicks appear here as soon as recipients interact with a sent email.
          </p>
        ) : (
          <ul className="mt-3 space-y-2 text-sm">
            {live.map((event, index) => (
              <li key={`${event.type}-${event.email_id}-${index}`}>
                {event.type.replaceAll("_", " ")}
                {event.recipient_email ? ` · ${event.recipient_email}` : ""}
                {event.destination_url ? ` · ${event.destination_url}` : ""}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
