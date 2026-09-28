"use client";

import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { authApi } from "@/lib/api/auth";
import { templatesApi } from "@/lib/api/templates";
import { ApiError } from "@/lib/api/client";
import type { TemplateAsset, User } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { TextArea, TextField } from "@/components/ui/field";
import { ErrorState, Notice, PageLoader } from "@/components/ui/states";

const blank = {
  name: "",
  subject: "",
  html_body:
    "<p>Hi {{first_name}},</p>\n<p>{{opener}}</p>\n<p>I would welcome a short conversation if this is useful for {{company}}.</p>\n<p>Best regards,<br>{{signoff}}</p>",
  text_body: "Hi {{first_name}},\n\n{{opener}}\n\nBest regards,\n{{signoff}}",
  ai_instructions:
    "Write one personal sentence to this person. Use you, not their job title, in the ask. Mention one real company fact from the last 30 days only when you can verify it, and leave it out when you cannot. Do not add a second hello or a sign-off.",
};

type InsertPosition = "cursor" | "top" | "bottom";

function imageSnippet(asset: TemplateAsset) {
  return `<img src="${asset.inline_placeholder}" alt="${asset.original_filename}" style="max-width:100%;height:auto;display:block;margin:16px 0;" />`;
}

function linkSnippet(asset: TemplateAsset) {
  return asset.link_placeholder;
}

function insertAt(html: string, snippet: string, position: InsertPosition, cursor: number | null) {
  const block = `\n<p>${snippet}</p>\n`;
  if (position === "top") return `${block}${html}`;
  if (position === "bottom" || cursor == null) return `${html}${block}`;
  return `${html.slice(0, cursor)}${block}${html.slice(cursor)}`;
}

export default function TemplateEditorPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const isNew = params.id === "new";
  const htmlRef = useRef<HTMLTextAreaElement>(null);
  const [form, setForm] = useState(blank);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [preview, setPreview] = useState("");
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState(false);
  const [pageLoading, setPageLoading] = useState(!isNew);
  const [previewing, setPreviewing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [insertingId, setInsertingId] = useState<string | null>(null);
  const [insertPosition, setInsertPosition] = useState<InsertPosition>("cursor");
  const [user, setUser] = useState<User | null>(null);
  const [assets, setAssets] = useState<TemplateAsset[]>([]);
  const [previewUrls, setPreviewUrls] = useState<Record<string, string>>({});

  useEffect(() => {
    authApi.me().then(setUser).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (isNew) return;
    templatesApi
      .get(params.id)
      .then(async (template) => {
        setForm({
          name: template.name,
          subject: template.subject,
          html_body: template.html_body,
          text_body: template.text_body,
          ai_instructions: template.ai_instructions ?? "",
        });
        setAssets(await templatesApi.listAssets(params.id));
      })
      .catch(() => setError("Unable to load template."))
      .finally(() => setPageLoading(false));
  }, [isNew, params.id]);

  useEffect(() => {
    let cancelled = false;

    async function loadPreviews() {
      const loaded: Record<string, string> = {};
      for (const asset of assets) {
        if (asset.kind !== "image") continue;
        if (previewUrls[asset.id]) continue;
        try {
          const url = await templatesApi.fetchAssetDataUrl(asset.id);
          if (cancelled) return;
          loaded[asset.id] = url;
          loaded[asset.placeholder_key] = url;
        } catch (err) {
          console.warn("Asset preview failed", asset.id, err);
        }
      }
      if (cancelled) return;
      if (Object.keys(loaded).length > 0) {
        setPreviewUrls((current) => ({ ...current, ...loaded }));
      }
    }

    void loadPreviews();
    return () => {
      cancelled = true;
    };
  }, [assets, previewUrls]);

  const sampleValues = useMemo(() => {
    const signoff = ["Best regards,", user?.full_name, user?.company_name].filter(Boolean).join("\n");
    return {
      first_name: "Ada",
      last_name: "Lovelace",
      company: "Northwind",
      title: "Operations Lead",
      industry: "Software",
      website: "https://northwind.example",
      opener:
        "Saw that Northwind is active in Software — figured this might be relevant to your team.",
      signoff,
    };
  }, [user]);

  const livePreview = useMemo(() => {
    let html = form.html_body;

    for (const asset of assets) {
      if (asset.kind === "pdf") {
        const escaped = asset.placeholder_key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        html = html.replace(
          new RegExp(`<p[^>]*>\\s*(?:<a\\b[^>]*>\\s*)?\\{\\{\\s*${escaped}\\s*\\}\\}\\s*(?:</a>\\s*)?</p>`, "gi"),
          "",
        );
        html = html.split(`{{${asset.placeholder_key}}}`).join("");
        continue;
      }
      const url =
        asset.preview_url || previewUrls[asset.id] || previewUrls[asset.placeholder_key];
      if (!url) continue;
      const escaped = asset.placeholder_key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const imageTag = `<img src="${url}" alt="${asset.original_filename.replace(/"/g, "")}" style="max-width:100%;height:auto;display:block;margin:16px 0;" />`;
      const linkTag = `<a href="${url}">${asset.original_filename}</a>`;
      html = html.replace(
        new RegExp(`<img\\b[^>]*\\{\\{\\s*${escaped}\\s*\\}\\}[^>]*>`, "gi"),
        () => imageTag,
      );
      html = html.replace(
        new RegExp(`<a\\b[^>]*\\{\\{\\s*${escaped}\\s*\\}\\}[^>]*>[\\s\\S]*?</a>`, "gi"),
        () => linkTag,
      );
      html = html.split(`{{${asset.placeholder_key}}}`).join(asset.kind === "image" ? imageTag : linkTag);
    }

    html = html.replace(/\{\{\s*asset_(?:img|link)_[a-zA-Z0-9]+\s*\}\}/g, "");

    html = html.replace(/\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g, (_, key: string) => {
      if (key.startsWith("asset_")) return "";
      const value = sampleValues[key as keyof typeof sampleValues] ?? "";
      return value.replaceAll("\n", "<br>");
    });

    return `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body style="margin:0;padding:24px;font-family:Arial,Helvetica,sans-serif;font-size:16px;line-height:1.65;color:#0a0b0d;background:#fff;">${html}</body></html>`;
  }, [form.html_body, sampleValues, assets, previewUrls]);

  const [frameUrl, setFrameUrl] = useState("");

  useEffect(() => {
    const blob = new Blob([livePreview], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    setFrameUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [livePreview]);

  function updateHtml(next: string) {
    setForm((current) => ({ ...current, html_body: next }));
    setPreview(""); // keep live preview in sync after edits/inserts
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      if (isNew) {
        const created = await templatesApi.create(form);
        router.replace(`/templates/${created.id}`);
      } else {
        await templatesApi.update(params.id, form);
        setNotice("Template saved.");
        setSaved(true);
        window.setTimeout(() => setSaved(false), 2500);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to save template.");
    } finally {
      setLoading(false);
    }
  }

  async function onUpload(file: File) {
    const html = await file.text();
    setForm((current) => ({
      ...current,
      html_body: html,
      name: current.name || file.name.replace(/\.html?$/i, ""),
    }));
    setPreview("");
  }

  async function onAssetUpload(file: File) {
    if (isNew) {
      setError("Save the template before uploading images or PDFs.");
      return;
    }
    setUploading(true);
    setError("");
    try {
      const localPreview =
        file.type.startsWith("image/") ? await templatesApi.fileToDataUrl(file) : "";
      const asset = await templatesApi.uploadAsset(params.id, file);
      setAssets((current) => [asset, ...current]);
      if (localPreview) {
        setPreviewUrls((current) => ({
          ...current,
          [asset.id]: localPreview,
          [asset.placeholder_key]: localPreview,
        }));
      }
      setNotice(
        asset.kind === "pdf"
          ? `Uploaded ${asset.original_filename}. It is attached to the email as a file, not inserted as a link.`
          : `Uploaded ${asset.original_filename}. Choose a position, then click Insert image.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  function insertPlaceholder(asset: TemplateAsset, asLink: boolean) {
    setInsertingId(asset.id);
    const snippet = asLink || asset.kind === "pdf" ? linkSnippet(asset) : imageSnippet(asset);
    const cursor = htmlRef.current?.selectionStart ?? form.html_body.length;
    const next = insertAt(form.html_body, snippet, insertPosition, cursor);
    updateHtml(next);
    const where =
      insertPosition === "top"
        ? "at the top"
        : insertPosition === "cursor"
          ? "at your cursor position"
          : "at the bottom";
    setNotice(
      `${asset.kind === "pdf" || asLink ? "Link" : "Image"} inserted ${where}. Scroll the live preview to confirm.`,
    );
    window.setTimeout(() => setInsertingId(null), 400);
    // Restore cursor near insert for further edits
    window.requestAnimationFrame(() => {
      const el = htmlRef.current;
      if (!el) return;
      el.focus();
      if (insertPosition === "cursor") {
        const point = cursor + `\n<p>${snippet}</p>\n`.length;
        el.setSelectionRange(point, point);
      }
    });
  }

  async function removeAsset(assetId: string) {
    if (!confirm("Delete this hosted file?")) return;
    await templatesApi.deleteAsset(assetId);
    setAssets((current) => current.filter((asset) => asset.id !== assetId));
    const key = Object.entries(previewUrls).find(([, url]) => url && assets.find((a) => a.id === assetId));
    void key;
  }

  async function runPreview() {
    if (isNew) {
      setError("Save the template before previewing.");
      return;
    }
    setPreviewing(true);
    try {
      await templatesApi.update(params.id, form);
      const result = await templatesApi.preview(params.id, {
        first_name: "Ada",
        last_name: "Lovelace",
        company: "Northwind",
        title: "Operations Lead",
        industry: "Software",
        website: "https://northwind.example",
      });
      // Still resolve images for server preview HTML which may still contain placeholders
      let html = result.html_body;
      for (const asset of assets) {
        const url = previewUrls[asset.id];
        if (!url) continue;
        const escaped = asset.placeholder_key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        html = html.replace(
          new RegExp(`src=["']\\{\\{\\s*${escaped}\\s*\\}\\}["']`, "g"),
          `src="${url}"`,
        );
        html = html.replace(
          new RegExp(`\\{\\{\\s*${escaped}\\s*\\}\\}`, "g"),
          asset.kind === "image"
            ? `<img src="${url}" alt="${asset.original_filename}" style="max-width:100%;height:auto;" />`
            : `<a href="${url}">${asset.original_filename}</a>`,
        );
      }
      setPreview(html);
      // Prefer live preview which already embeds data URLs
      setPreview("");
      setNotice("Saved for send preview. Live preview below already shows images.");
    } finally {
      setPreviewing(false);
    }
  }

  if (pageLoading) return <PageLoader label="Loading template" />;

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-normal tracking-tight">{isNew ? "New template" : "Edit template"}</h1>
      {notice ? <Notice>{notice}</Notice> : null}
      {error ? <ErrorState message={error} /> : null}
      <form onSubmit={onSubmit} className="space-y-4 rounded-3xl border border-hairline bg-canvas p-6">
        <TextField
          label="Name"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          required
        />
        <TextField
          label="Subject"
          value={form.subject}
          onChange={(e) => setForm({ ...form, subject: e.target.value })}
          required
        />
        <label className="block space-y-2">
          <span className="text-sm font-semibold">Upload HTML</span>
          <input
            type="file"
            accept=".html,text/html"
            className="block w-full text-sm"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void onUpload(file);
            }}
          />
        </label>
        <TextArea
          ref={htmlRef}
          label="HTML body"
          value={form.html_body}
          onChange={(e) => updateHtml(e.target.value)}
          hint="The saved HTML keeps {{asset_img_…}} so each recipient gets a tracked link. The preview below shows the real image."
        />
        <TextArea
          label="Plain text"
          value={form.text_body}
          onChange={(e) => setForm({ ...form, text_body: e.target.value })}
        />
        <TextArea
          label="AI instructions"
          value={form.ai_instructions}
          onChange={(e) => setForm({ ...form, ai_instructions: e.target.value })}
        />
        <p className="text-sm text-muted">
          With AI on, each send rewrites this template for that person: name, title, company, website,
          and one real recent public news item when search finds one. Placeholders such as {" "}
          {"{{first_name}}"}, {"{{company}}"}, {"{{opener}}"}, and image placeholders stay available.
        </p>
        <div className="flex gap-3">
          <Button type="submit" loading={loading}>
            {saved ? "Saved" : "Save"}
          </Button>
          <Button type="button" variant="secondary" loading={previewing} onClick={runPreview}>
            Preview
          </Button>
        </div>
      </form>

      <section className="rounded-3xl border border-hairline bg-canvas p-6">
        <h2 className="text-lg font-semibold">Hosted images & PDFs</h2>
        <p className="mt-1 text-sm text-muted">
          Upload a file, choose where it should appear, then insert it. The live preview shows the real
          image. In the sent email, each recipient gets a unique tracked URL.
        </p>
        {isNew ? (
          <p className="mt-3 text-sm text-muted">Save the template first to upload assets.</p>
        ) : (
          <>
            <div className="mt-4 flex flex-wrap items-end gap-3">
              <label className="block space-y-2">
                <span className="text-sm font-semibold">Upload image or PDF</span>
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/gif,image/webp,application/pdf,.pdf,.png,.jpg,.jpeg,.gif,.webp"
                  className="block w-full text-sm"
                  disabled={uploading}
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void onAssetUpload(file);
                    event.target.value = "";
                  }}
                />
              </label>
              <label className="block space-y-2">
                <span className="text-sm font-semibold">Insert position</span>
                <select
                  className="h-12 rounded-xl border border-hairline bg-canvas px-3 text-sm"
                  value={insertPosition}
                  onChange={(event) => setInsertPosition(event.target.value as InsertPosition)}
                >
                  <option value="cursor">At cursor in HTML body</option>
                  <option value="top">Top of email</option>
                  <option value="bottom">Bottom of email</option>
                </select>
              </label>
            </div>
            {uploading ? <p className="mt-3 text-sm text-muted">Uploading…</p> : null}
            {assets.length === 0 ? (
              <p className="mt-4 text-sm text-muted">No hosted files yet.</p>
            ) : (
              <ul className="mt-4 space-y-3">
                {assets.map((asset) => (
                  <li
                    key={asset.id}
                    className="flex flex-col gap-3 rounded-2xl border border-hairline px-4 py-3 md:flex-row md:items-center md:justify-between"
                  >
                    <div className="flex items-start gap-3">
                      {asset.kind === "image" && (asset.preview_url || previewUrls[asset.id]) ? (
                        <img
                          src={asset.preview_url || previewUrls[asset.id]}
                          alt={asset.original_filename}
                          className="h-16 w-16 rounded-lg object-cover border border-hairline"
                        />
                      ) : (
                        <div className="flex h-16 w-16 items-center justify-center rounded-lg border border-hairline bg-surface-soft text-xs text-muted">
                          {asset.kind === "pdf" ? "PDF" : "IMG"}
                        </div>
                      )}
                      <div>
                        <p className="font-medium">
                          {asset.original_filename}{" "}
                          <span className="text-sm text-muted">({asset.kind})</span>
                        </p>
                        <p className="mt-1 text-xs text-muted">
                          Placeholder: <code>{asset.inline_placeholder}</code>
                        </p>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {asset.kind === "pdf" ? (
                        <p className="text-sm text-muted">Attached to every email as a file.</p>
                      ) : (
                        <Button
                          type="button"
                          variant="secondary"
                          loading={insertingId === asset.id}
                          onClick={() => insertPlaceholder(asset, false)}
                        >
                          Insert image
                        </Button>
                      )}
                      {asset.kind !== "pdf" ? (
                        <Button
                          type="button"
                          variant="secondary"
                          onClick={() => insertPlaceholder(asset, true)}
                        >
                          Insert as link
                        </Button>
                      ) : null}
                      <Button type="button" variant="danger" onClick={() => void removeAsset(asset.id)}>
                        Delete
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </section>

      <section className="rounded-3xl border border-hairline bg-canvas p-6">
        <h2 className="text-lg font-semibold">Live preview</h2>
        <p className="mt-1 text-sm text-muted">
          Variables and hosted images are resolved here. PDFs are attached to the message, the same way a
          file is attached in Gmail, and are not shown as links.
        </p>
        {assets.some((asset) => asset.kind === "pdf") ? (
          <p className="mt-3 text-sm">
            Attached:{" "}
            {assets
              .filter((asset) => asset.kind === "pdf")
              .map((asset) => asset.original_filename)
              .join(", ")}
          </p>
        ) : null}
        <p className="mt-3 whitespace-pre-line rounded-2xl bg-surface-soft px-4 py-3 text-sm">
          <span className="font-semibold text-ink">Resolved sign-off</span>
          {"\n"}
          {sampleValues.signoff || "Add your name in Settings to complete the sign-off."}
        </p>
        <iframe
          title="Template preview"
          className="mt-4 h-[640px] w-full rounded-2xl border border-hairline bg-white"
          src={frameUrl || undefined}
        />
      </section>
    </div>
  );
}
