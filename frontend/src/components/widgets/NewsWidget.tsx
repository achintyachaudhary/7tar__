import { useCallback, useState } from "react";
import { fetchFollowingNews, type NewsArticle } from "../../api";
import { useLiveRefresh } from "../../hooks/useLiveRefresh";
import { displaySymbol } from "../../utils/tradingView";
import TimestampLabel from "../TimestampLabel";

const SIZE_LIMIT: Record<string, number> = { sm: 6, md: 10, lg: 18 };

function timeAgo(ms: number | null): string {
  if (!ms) return "";
  const mins = Math.round((Date.now() - ms) / 60_000);
  if (mins < 60) return `${Math.max(1, mins)}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export default function NewsWidget({ size = "md" }: { size?: string }) {
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [symbols, setSymbols] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetchFollowingNews();
      setArticles(res.articles);
      setSymbols(res.symbols);
      setFetchedAt(new Date());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);
  useLiveRefresh(load, { liveMs: 10 * 60_000, closedMs: 20 * 60_000 });

  if (loading) return <div className="widget-loading">Loading news…</div>;
  if (error) return <div className="widget-error">{error}</div>;

  if (symbols.length === 0) {
    return (
      <div className="widget-empty">
        Follow stocks to build your news feed — search any stock above and hit
        the 🔔 Follow button.
      </div>
    );
  }

  if (articles.length === 0) {
    return (
      <div className="widget-empty">
        No recent news for {symbols.map(displaySymbol).join(", ")}.
      </div>
    );
  }

  return (
    <div className="news-widget">
      <div className="news-widget-following">
        Following: {symbols.map(displaySymbol).join(" · ")}
      </div>
      <ul className="news-widget-list">
        {articles.slice(0, SIZE_LIMIT[size] ?? 10).map((a, i) => (
          <li key={`${a.article_link}-${i}`} className="news-widget-item">
            <div className="news-widget-meta">
              <span className="news-widget-symbol">{displaySymbol(a.symbol)}</span>
              <span className="news-widget-time">{timeAgo(a.published_time)}</span>
            </div>
            <a
              className="news-widget-heading"
              href={a.article_link ?? "#"}
              target="_blank"
              rel="noopener noreferrer"
              title={a.summary ?? undefined}
            >
              {a.heading}
            </a>
          </li>
        ))}
      </ul>
      <div className="widget-as-of">
        <TimestampLabel at={fetchedAt} label="Fetched" />
        <span className="widget-as-of-note"> · via Upstox News API</span>
      </div>
    </div>
  );
}
