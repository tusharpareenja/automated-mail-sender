"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { templatesApi } from "@/lib/api/templates";
import type { Template } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, PageLoader } from "@/components/ui/states";

export default function TemplatesPage() {
  const [items, setItems] = useState<Template[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function refresh() {
    try {
      setItems(await templatesApi.list());
    } catch {
      setError("Unable to load templates.");
    }
  }

  useEffect(() => {
    let active = true;
    templatesApi
      .list()
      .then((rows) => {
        if (active) setItems(rows);
      })
      .catch(() => {
        if (active) setError("Unable to load templates.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-normal tracking-tight">Templates</h1>
          <p className="mt-2 text-body">Create, upload, duplicate, and preview reusable emails.</p>
        </div>
        <Link href="/templates/new">
          <Button>New template</Button>
        </Link>
      </div>
      {error ? <ErrorState message={error} /> : null}
      {loading ? <PageLoader label="Loading templates" /> : items.length === 0 ? (
        <EmptyState title="No templates" body="Start with a simple HTML template and variables like {{first_name}}." />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {items.map((template) => (
            <article key={template.id} className="rounded-3xl border border-hairline bg-canvas p-6">
              <h2 className="text-lg font-semibold">{template.name}</h2>
              <p className="mt-2 text-sm text-body">{template.subject}</p>
              <p className="mt-3 text-xs text-muted">Variables: {template.variables.join(", ") || "none"}</p>
              <div className="mt-4 flex gap-2">
                <Link href={`/templates/${template.id}`} className="text-sm font-semibold text-primary">
                  Edit
                </Link>
                <button
                  type="button"
                  className="cursor-pointer text-sm font-semibold text-body"
                  onClick={async () => {
                    await templatesApi.duplicate(template.id);
                    await refresh();
                  }}
                >
                  Duplicate
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
