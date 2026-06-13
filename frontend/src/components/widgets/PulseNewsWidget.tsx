import { useCallback, useEffect, useState } from "react";
import {
  fetchPulseNews,
  triggerPulseRefresh,
  type PulseNewsResponse,
} from "../../api";
import { useLiveRefresh } from "../../hooks/useLiveRefresh";

const SIZE_LIMIT: Record<string, number> = { sm: 5, md: 8, lg: 14 };

function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return "";
  const mins = Math.round((Date.now() - ms) / 60_000);
  if (mins < 60) return `${Math.max(1, mins)}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export default function PulseNewsWidget({ size = "md" }: { size?: string }) {
  const [data, setData] = useState<PulseNewsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetchPulseNews();
      setData(res);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);
  useLiveRefresh(load, { liveMs: 5 * 60_000, closedMs: 15 * 60_000 });

  // poll faster while a fetch+summarize run is in progress
  useEffect(() => {
    if (!data?.running) return;
    const t = window.setTimeout(load, 5_000);
    return () => window.clearTimeout(t);
  }, [data, load]);

  async function handleFetchNow() {
    try {
      await triggerPulseRefresh();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  if (loading) return <div className="widget-loading">Loading Pulse news…</div>;
  if (error && !data) return <div className="widget-error">{error}</div>;

  const items = data?.items ?? [];
  const run = data?.last_run;

  return (
    <div className="pulse-news-widget">
      <div className="pulse-news-toolbar">
        <span className="pulse-news-sourcenote">
          via{" "}
          <a href="https://pulse.zerodha.com/" target="_blank" rel="noopener noreferrer">
            Pulse by Zerodha
          </a>
          {" · "}auto-refresh every 30m
        </span>
        <button
          type="button"
          className="pulse-news-fetch-btn"
          onClick={handleFetchNow}
          disabled={data?.running}
          title="Fetch the feed and summarize new items now"
        >
          {data?.running ? "⏳ Summarizing…" : "⟳ Fetch now"}
        </button>
      </div>

      {run?.status === "error" && (
        <div className="widget-error">Last run failed: {run.error}</div>
      )}

      {items.length === 0 ? (
        <div className="widget-empty">
          No news yet — hit <strong>Fetch now</strong> to pull and summarize the
          latest Pulse headlines.
        </div>
      ) : (
        <ul className="pulse-news-list">
          {items.slice(0, SIZE_LIMIT[size] ?? 8).map((item, i) => (
            <li key={`${item.link}-${i}`} className="pulse-news-item">
              <div className="pulse-news-meta">
                <span className="pulse-news-source">{item.source}</span>
                <span className="pulse-news-time">{timeAgo(item.published_at)}</span>
              </div>
              <a
                className="pulse-news-headline"
                href={item.link ?? "#"}
                target="_blank"
                rel="noopener noreferrer"
              >
                {item.title}
              </a>
              {item.summary && (
                <div className="pulse-news-summary">
                  <span
                    className="pulse-ai-badge"
                    title={`Summarized by local AI (${item.model ?? "LLM"})`}
                  >
                    ✨ AI
                  </span>
                  {item.summary}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {run && (
        <div className="widget-as-of">
          Last run ({run.triggered_by}): {timeAgo(run.finished_at ?? run.started_at)}
          {run.status === "success" && ` · ${run.items_new} new summarized`}
          <span className="widget-as-of-note"> · summaries are AI-generated</span>
        </div>
      )}
    </div>
  );
}
