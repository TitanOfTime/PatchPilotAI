"use client";
import {
  ChevronDown,
  FileCode2,
  ExternalLink,
  Check,
  Clock3,
  Loader2,
  CircleAlert,
  Minus,
} from "lucide-react";
import type { Evidence } from "@/lib/api";
export function StatusLabel({ value }: { value: string }) {
  const labels: Record<string, string> = {
    ready: "Indexed",
    registered: "Not indexed",
    awaiting_review: "Needs review",
    test_passed: "Tests passed",
    test_failed: "Tests failed",
    human_rejected: "Declined",
    validated: "Patch checked",
    enabled: "On",
    disabled: "Off",
    embedding: "Indexing source",
    cloning: "Cloning repository",
    resuming: "Resuming",
  };
  const failed = /error|failed|rejected/.test(value);
  const working = /running|queued|cloning|embedding|resuming|testing/.test(
    value,
  );
  const successful =
    /ready|passed|approved|connected|completed|validated|grounded/.test(value);
  const Icon = failed
    ? CircleAlert
    : working
      ? Loader2
      : successful
        ? Check
        : /review/.test(value)
          ? Clock3
          : Minus;
  return (
    <span
      className={`status-label ${failed ? "status-error" : working ? "status-working" : successful ? "status-success" : "status-neutral"}`}
    >
      <Icon
        size={13}
        strokeWidth={1.7}
        className={working ? "spin" : undefined}
        aria-hidden="true"
      />
      {labels[value] ?? value.replaceAll("_", " ")}
    </span>
  );
}
export function EvidenceCards({ items }: { items: Evidence[] }) {
  return (
    <div className="evidence-list">
      {items.map((e, i) => (
        <details className="evidence" key={e.id}>
          <summary>
            <span className="file-icon">
              <FileCode2 size={16} />
            </span>
            <span className="file-label">
              <strong>{e.path.split("/").pop()}</strong>
              <small>{e.path}</small>
            </span>
            <span className="line-ref">
              L{e.start_line}–{e.end_line}
            </span>
            <ChevronDown size={15} />
          </summary>
          <div className="evidence-meta">
            <span>
              Evidence {i + 1} · {e.sha.slice(0, 8)} · RRF {e.score.toFixed(4)}
            </span>
            {e.url.startsWith("https://github.com/") && (
              <a target="_blank" rel="noreferrer" href={e.url}>
                View source <ExternalLink size={12} />
              </a>
            )}
          </div>
          <pre className="source">
            {e.content.split("\n").map((line, n) => (
              <span className="code-line" key={n}>
                <i>{n + e.start_line}</i>
                {line}
                {"\n"}
              </span>
            ))}
          </pre>
        </details>
      ))}
    </div>
  );
}
