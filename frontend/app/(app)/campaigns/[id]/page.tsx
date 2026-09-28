"use client";

import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { campaignsApi } from "@/lib/api/campaigns";
import { ApiError } from "@/lib/api/client";
import type {
  Campaign,
  CampaignAnalytics,
  CampaignEmail,
  CampaignPreview,
  LiveEvent,
  OpenClassification,
} from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/field";
import { ErrorState, Notice, PageLoader } from "@/components/ui/states";
import { useRealtimeEvents } from "@/lib/realtime/useRealtimeEvents";

function labelFor(type: string) {
  if (type === "EMAIL_OPENED" || type === "OPENED") return "Opened";
  if (type === "EMAIL_OPEN_REQUEST" || type === "OPEN_REQUEST") return "Open request";
  if (type === "LINK_CLICKED" || type === "CLICKED") return "Link clicked";
  if (type === "ASSET_IMAGE_LOADED" || type === "IMAGE_LOADED") return "Image loaded";
  if (type === "ASSET_PDF_ACCESSED" || type === "PDF_ACCESSED") return "PDF accessed";
  if (type === "EMAIL_SENT" || type === "SENT") return "Email sent";
  if (type === "EMAIL_FAILED" || type === "FAILED") return "Email failed";
  return type;
}

function openLabel(classification: OpenClassification | string) {
  if (classification === "likely_automated" || classification === "automated") {
    return "Likely automated";
  }
  if (!classification || classification === "none") return "No open signal";
  return "Opened";
}

function requestTypeLabel(type: string) {
  if (type === "open_pixel") return "Pixel load";
  if (type === "view_email") return "Web view";
  if (type === "link_click") return "Link click";
  if (type === "image_loaded") return "Image opened";
  if (type === "pdf_accessed") return "PDF opened";
  if (type === "download_requested") return "Download";
  return type;
}

export default function CampaignDetailPage() {
  const params = useParams<{ id: string }>();
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [emails, setEmails] = useState<CampaignEmail[]>([]);
  const [analytics, setAnalytics] = useState<CampaignAnalytics | null>(null);
  const [previews, setPreviews] = useState<CampaignPreview[]>([]);
  const [live, setLive] = useState<LiveEvent[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [testEmail, setTestEmail] = useState("");
  const [busy, setBusy] = useState("");
  const [trackingLocal, setTrackingLocal] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const recentLive = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    let active = true;
    Promise.all([
      campaignsApi.get(params.id),
      campaignsApi.emails(params.id),
      campaignsApi.analytics(params.id, { silent: true }),
      campaignsApi.trackingStatus().catch(() => null),
    ])
      .then(([data, emailRows, analyticsRows, tracking]) => {
        if (!active) return;
        setCampaign(data);
        setEmails(emailRows);
        setAnalytics(analyticsRows);
        if (tracking) setTrackingLocal(tracking.is_local);
      })
      .catch(() => {
        if (active) setError("Unable to load campaign.");
      });
    return () => {
      active = false;
    };
  }, [params.id]);

  const socketStatus = useRealtimeEvents((event) => {
    if (event.type === "CONNECTED") return;
    if (event.campaign_id && event.campaign_id !== params.id) return;

    if (event.type === "CAMPAIGN_COMPLETED" || event.type === "CAMPAIGN_STATUS") {
      setCampaign((current) =>
        current
          ? { ...current, status: event.status || "COMPLETED", queued_count: 0 }
          : current,
      );
      return;
    }

    const kind =
      event.type === "EMAIL_OPENED" || event.type === "EMAIL_OPEN_REQUEST" ? "OPEN" : event.type;
    const dedupeKey = `${kind}|${event.email_id ?? ""}|${event.recipient_email ?? ""}`;
    const now = Date.now();
    const seenAt = recentLive.current.get(dedupeKey) ?? 0;
    if (now - seenAt < 8000) return;
    recentLive.current.set(dedupeKey, now);
    const stamped = { ...event, created_at: new Date().toISOString() };
    setLive((current) => [stamped, ...current].slice(0, 30));

    setCampaign((current) => {
      if (!current) return current;
      if (event.type === "EMAIL_OPENED") {
        return { ...current, open_count: current.open_count + 1 };
      }
      if (event.type === "LINK_CLICKED") return { ...current, click_count: current.click_count + 1 };
      if (event.type === "EMAIL_SENT") {
        return {
          ...current,
          sent_count: current.sent_count + 1,
          queued_count: Math.max(0, current.queued_count - 1),
        };
      }
      if (event.type === "EMAIL_FAILED") {
        return {
          ...current,
          failed_count: current.failed_count + 1,
          queued_count: Math.max(0, current.queued_count - 1),
        };
      }
      if (event.type === "EMAIL_UNSUBSCRIBED") {
        return { ...current, unsubscribe_count: current.unsubscribe_count + 1 };
      }
      return current;
    });

    setAnalytics((current) => {
      if (!current) return current;
      if (event.type === "EMAIL_SENT") {
        return {
          ...current,
          sent: current.sent + 1,
          queued: Math.max(0, current.queued - 1),
        };
      }
      if (event.type === "EMAIL_FAILED") {
        return {
          ...current,
          failed: current.failed + 1,
          queued: Math.max(0, current.queued - 1),
        };
      }
      if (event.type === "EMAIL_OPENED") {
        return { ...current, tracked_opens: current.tracked_opens + 1 };
      }
      if (event.type === "EMAIL_OPEN_REQUEST") {
        return { ...current, open_requests: current.open_requests + 1 };
      }
      if (event.type === "LINK_CLICKED") return { ...current, clicks: current.clicks + 1 };
      if (event.type === "ASSET_IMAGE_LOADED") {
        return { ...current, image_loads: current.image_loads + 1 };
      }
      if (event.type === "ASSET_PDF_ACCESSED") {
        return { ...current, pdf_accesses: current.pdf_accesses + 1 };
      }
      if (event.type === "ASSET_DOWNLOAD_REQUESTED") {
        return { ...current, downloads: current.downloads + 1 };
      }
      if (event.type === "EMAIL_UNSUBSCRIBED") {
        return { ...current, unsubscribes: current.unsubscribes + 1 };
      }
      return current;
    });

    setEmails((current) =>
      current.map((row) => {
        if (row.id !== event.email_id) return row;
        if (event.type === "EMAIL_OPENED" || event.type === "EMAIL_OPEN_REQUEST") {
          const raw = event.classification ?? "proxy_or_uncertain";
          const mapped: OpenClassification =
            raw === "automated"
              ? "likely_automated"
              : (raw as OpenClassification);
          return {
            ...row,
            opened: true,
            opened_at: row.opened_at ?? new Date().toISOString(),
            latest_open_at: new Date().toISOString(),
            open_classification: mapped,
            open_request_count: row.open_request_count + (event.type === "EMAIL_OPEN_REQUEST" ? 1 : 0),
            open_reasons: event.reasons ?? row.open_reasons,
            open_confidence: event.confidence ?? row.open_confidence,
          };
        }
        if (event.type === "LINK_CLICKED") {
          return {
            ...row,
            clicked: true,
            click_count: row.click_count + 1,
            links: row.links.map((link) =>
              event.destination_url && link.destination_url === event.destination_url
                ? { ...link, clicked: true, click_count: link.click_count + 1 }
                : link,
            ),
          };
        }
        if (
          event.type === "ASSET_IMAGE_LOADED" ||
          event.type === "ASSET_PDF_ACCESSED" ||
          event.type === "ASSET_DOWNLOAD_REQUESTED"
        ) {
          return {
            ...row,
            assets: row.assets.map((asset) => {
              if (event.asset_id && asset.asset_id !== event.asset_id) return asset;
              return {
                ...asset,
                access_count: asset.access_count + 1,
                image_loads:
                  asset.image_loads + (event.type === "ASSET_IMAGE_LOADED" ? 1 : 0),
                pdf_accesses:
                  asset.pdf_accesses + (event.type === "ASSET_PDF_ACCESSED" ? 1 : 0),
                downloads:
                  asset.downloads + (event.type === "ASSET_DOWNLOAD_REQUESTED" ? 1 : 0),
                download_count:
                  asset.download_count +
                  (event.type === "ASSET_DOWNLOAD_REQUESTED" ? 1 : 0),
              };
            }),
          };
        }
        if (event.type === "EMAIL_SENT") return { ...row, status: "SENT" };
        if (event.type === "EMAIL_FAILED") return { ...row, status: "FAILED" };
        return row;
      }),
    );
  });

  const socketState =
    socketStatus === "live"
      ? "Live"
      : socketStatus === "connecting"
        ? "Connecting live updates..."
        : socketStatus === "offline"
          ? "Reconnecting..."
          : "Live updates idle";

  async function run(action: "start" | "pause" | "resume" | "cancel") {
    try {
      if (action === "start" && !confirm("Launch this campaign? Emails will begin sending through your workers.")) {
        return;
      }
      setBusy(action);
      const updated = await campaignsApi[action](params.id);
      setCampaign(updated);
      setNotice(`Campaign is now ${updated.status}.`);
      const [emailRows, analyticsRows] = await Promise.all([
        campaignsApi.emails(params.id),
        campaignsApi.analytics(params.id, { silent: true }),
      ]);
      setEmails(emailRows);
      setAnalytics(analyticsRows);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Campaign action failed.");
    } finally {
      setBusy("");
    }
  }

  if (error && !campaign) return <ErrorState message={error} />;
  if (!campaign) return <PageLoader label="Loading campaign" />;

  const sentCount = emails.filter((email) => email.status === "SENT").length;
  const queuedCount = emails.filter((email) =>
    ["QUEUED", "SENDING", "GENERATING", "READY"].includes(email.status),
  ).length;
  const failedCount = emails.filter((email) => email.status === "FAILED").length;
  const openedCount = emails.filter(
    (email) => email.opened || (email.open_classification && email.open_classification !== "none"),
  ).length;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-3xl font-normal tracking-tight">{campaign.name}</h1>
          <p className="mt-2 text-body">
            Status: {campaign.status} · {socketState}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {campaign.status === "DRAFT" ? (
            <Button loading={busy === "start"} onClick={() => run("start")}>
              Launch
            </Button>
          ) : null}
          {campaign.status === "RUNNING" ? (
            <Button variant="secondary" loading={busy === "pause"} onClick={() => run("pause")}>
              Pause
            </Button>
          ) : null}
          {campaign.status === "PAUSED" ? (
            <Button loading={busy === "resume"} onClick={() => run("resume")}>
              Resume
            </Button>
          ) : null}
          {["DRAFT", "QUEUED", "RUNNING", "PAUSED"].includes(campaign.status) ? (
            <Button variant="danger" loading={busy === "cancel"} onClick={() => run("cancel")}>
              Cancel
            </Button>
          ) : null}
        </div>
      </div>
      {notice ? <Notice>{notice}</Notice> : null}
      {trackingLocal ? (
        <Notice>
          Open tracking needs a public HTTPS URL. Gmail cannot reach localhost, so opens stay at 0 until
          TRACKING_PUBLIC_URL is set to a tunnel or deployed API and you send a new campaign.
        </Notice>
      ) : null}
      {error ? <ErrorState message={error} /> : null}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ["Queued", emails.length ? queuedCount : campaign.queued_count],
          ["Sent", emails.length ? sentCount : campaign.sent_count],
          ["Failed", emails.length ? failedCount : campaign.failed_count],
          ["Opened", emails.length ? openedCount : campaign.open_count],
          ["Clicks", campaign.click_count],
          ["Images loaded", analytics?.image_loads ?? 0],
          ["PDFs accessed", analytics?.pdf_accesses ?? 0],
        ].map(([label, value]) => (
          <article key={String(label)} className="rounded-3xl border border-hairline bg-canvas p-5">
            <p className="text-sm text-muted">{label}</p>
            <p className="tabular mt-2 text-2xl">{value}</p>
          </article>
        ))}
      </section>

      <section className="rounded-3xl border border-hairline bg-canvas p-6">
        <h2 className="font-semibold">Recipient evidence</h2>
        <p className="mt-1 text-sm text-muted">
          An open in the first 30 seconds after send is marked Likely automated. Later opens are marked
          Opened.
        </p>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="text-muted">
                <th className="px-3 py-2">Recipient</th>
                <th className="px-3 py-2">Delivery</th>
                <th className="px-3 py-2">Open evidence</th>
                <th className="px-3 py-2">Links & assets</th>
              </tr>
            </thead>
            <tbody>
              {emails.map((email) => (
                <tr key={email.id} className="border-t border-hairline align-top">
                  <td className="px-3 py-3">
                    <p className="font-medium">{email.recipient_email}</p>
                    <p className="text-xs text-muted">{email.subject}</p>
                    <button
                      type="button"
                      className="mt-2 text-xs underline"
                      onClick={() => setExpanded(expanded === email.id ? null : email.id)}
                    >
                      {expanded === email.id ? "Hide timeline" : "Show request timeline"}
                    </button>
                    {expanded === email.id ? (
                      <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto text-xs text-muted">
                        {email.requests.length === 0 ? (
                          <li>No tracking requests yet.</li>
                        ) : (
                          email.requests.map((req) => (
                            <li key={req.id}>
                              {new Date(req.created_at).toLocaleString()} ·{" "}
                              {requestTypeLabel(req.request_type)} · {openLabel(req.classification)}
                              {req.filename ? ` · ${req.filename}` : ""}
                            </li>
                          ))
                        )}
                      </ul>
                    ) : null}
                  </td>
                  <td className="px-3 py-3">{email.status}</td>
                  <td className="px-3 py-3">
                    <p>{openLabel(email.open_classification)}</p>
                    {email.opened_at ? (
                      <p className="mt-1 text-xs text-muted">
                        First: {new Date(email.opened_at).toLocaleString()}
                      </p>
                    ) : null}
                    {email.latest_open_at ? (
                      <p className="text-xs text-muted">
                        Latest: {new Date(email.latest_open_at).toLocaleString()}
                      </p>
                    ) : null}
                    <p className="mt-1 text-xs text-muted">
                      {email.open_request_count} request
                      {email.open_request_count === 1 ? "" : "s"}
                    </p>
                  </td>
                  <td className="px-3 py-3">
                    {email.links.length === 0 && email.assets.length === 0 ? (
                      <span className="text-muted">No tracked links or assets</span>
                    ) : (
                      <ul className="space-y-1">
                        {email.links.map((link) => (
                          <li key={link.destination_url}>
                            {link.clicked ? "Clicked" : "Not clicked"} · {link.click_count} ·{" "}
                            {link.destination_url}
                          </li>
                        ))}
                        {email.assets.map((asset) => (
                          <li key={asset.asset_id}>
                            {asset.kind === "image" ? "Image" : asset.kind === "pdf" ? "PDF" : "File"}{" "}
                            {asset.filename}: {asset.image_loads} loads · {asset.pdf_accesses} PDF ·{" "}
                            {asset.downloads} downloads
                          </li>
                        ))}
                      </ul>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-3xl border border-hairline bg-canvas p-6">
        <h2 className="font-semibold">Asset analytics</h2>
        <p className="mt-1 text-sm text-muted">
          Hosted images and PDFs report when the tracked URL is fetched — not whether the file was read offline.
        </p>
        {(analytics?.assets?.length ?? 0) === 0 ? (
          <p className="mt-3 text-sm text-muted">No hosted asset activity for this campaign yet.</p>
        ) : (
          <ul className="mt-4 space-y-2 text-sm">
            {analytics?.assets.map((asset) => (
              <li key={asset.asset_id} className="rounded-2xl border border-hairline px-4 py-3">
                <p className="font-medium">
                  {asset.filename}{" "}
                  <span className="text-muted">({asset.kind})</span>
                </p>
                <p className="mt-1 text-muted">
                  Image loads {asset.image_loads} · PDF accesses {asset.pdf_accesses}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-3xl border border-hairline bg-canvas p-6">
        <h2 className="font-semibold">Live events</h2>
        {live.length === 0 ? (
          <p className="mt-2 text-sm text-muted">
            Waiting for open requests, clicks, asset access, sends, and unsubscribes.
          </p>
        ) : (
          <ul className="mt-3 space-y-2 text-sm">
            {live.map((event, index) => (
              <li key={`${event.type}-${event.email_id}-${index}`}>
                {event.type === "EMAIL_OPENED" || event.type === "EMAIL_OPEN_REQUEST"
                  ? openLabel(event.classification ?? "opened")
                  : labelFor(event.type)}
                {event.recipient_email ? ` · ${event.recipient_email}` : ""}
                {event.filename ? ` · ${event.filename}` : ""}
                {event.destination_url ? ` · ${event.destination_url}` : ""}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-3xl border border-hairline bg-canvas p-6">
        <h2 className="font-semibold">Event timeline</h2>
        {(analytics?.timeline?.length ?? 0) === 0 ? (
          <p className="mt-2 text-sm text-muted">No stored events yet.</p>
        ) : (
          <ul className="mt-3 max-h-80 space-y-2 overflow-y-auto text-sm">
            {analytics?.timeline.map((event) => (
              <li key={event.id}>
                {new Date(event.created_at).toLocaleString()} ·{" "}
                {event.event_type === "OPENED" ||
                event.event_type === "OPEN_REQUEST" ||
                event.event_type === "EMAIL_OPENED" ||
                event.event_type === "EMAIL_OPEN_REQUEST"
                  ? openLabel(event.classification ?? "opened")
                  : labelFor(event.event_type)}
                {event.recipient_email ? ` · ${event.recipient_email}` : ""}
                {event.filename ? ` · ${event.filename}` : ""}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-3xl border border-hairline bg-canvas p-6">
        <h2 className="font-semibold">Preview and test</h2>
        <div className="mt-4 flex flex-col gap-3 md:flex-row">
          <Button
            variant="secondary"
            loading={busy === "preview"}
            onClick={async () => {
              setBusy("preview");
              try {
                setPreviews(await campaignsApi.preview(campaign.id));
              } finally {
                setBusy("");
              }
            }}
          >
            Generate preview
          </Button>
          <TextField
            label="Test recipient"
            value={testEmail}
            onChange={(event) => setTestEmail(event.target.value)}
          />
          <Button
            variant="secondary"
            loading={busy === "test"}
            onClick={async () => {
              setBusy("test");
              try {
                await campaignsApi.testEmail(campaign.id, testEmail);
                setNotice("Test email sent.");
              } finally {
                setBusy("");
              }
            }}
          >
            Send test email
          </Button>
        </div>
        {previews.map((preview) => (
          <article key={preview.lead_id} className="mt-4 rounded-2xl border border-hairline p-4">
            <p className="text-sm text-muted">{preview.email}</p>
            <p className="font-semibold">{preview.subject}</p>
            <iframe
              title={`Preview ${preview.email}`}
              className="mt-3 h-[480px] w-full rounded-2xl border border-hairline bg-white"
              srcDoc={preview.html_body}
            />
          </article>
        ))}
      </section>
    </div>
  );
}
