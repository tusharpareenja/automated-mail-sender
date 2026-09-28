"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { campaignsApi } from "@/lib/api/campaigns";
import type { Campaign } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, PageLoader } from "@/components/ui/states";

export default function CampaignsPage() {
  const [items, setItems] = useState<Campaign[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    campaignsApi
      .list()
      .then(setItems)
      .catch(() => setError("Unable to load campaigns."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <PageLoader label="Loading campaigns" />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-normal tracking-tight">Campaigns</h1>
          <p className="mt-2 text-body">Create, launch, pause, and monitor sending.</p>
        </div>
        <Link href="/campaigns/new">
          <Button>New campaign</Button>
        </Link>
      </div>
      {error ? <ErrorState message={error} /> : null}
      {items.length === 0 ? (
        <EmptyState title="No campaigns" body="Connect SMTP, create a template, import leads, then launch." />
      ) : (
        <div className="overflow-x-auto rounded-3xl border border-hairline bg-canvas">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="text-muted">
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Sent</th>
                <th className="px-4 py-3">Failed</th>
              </tr>
            </thead>
            <tbody>
              {items.map((campaign) => (
                <tr key={campaign.id} className="border-t border-hairline">
                  <td className="px-4 py-3">
                    <Link href={`/campaigns/${campaign.id}`} className="font-medium text-primary">
                      {campaign.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3">{campaign.status}</td>
                  <td className="tabular px-4 py-3">{campaign.sent_count}</td>
                  <td className="tabular px-4 py-3">{campaign.failed_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
