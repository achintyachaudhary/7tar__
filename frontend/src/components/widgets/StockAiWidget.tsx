import { useEffect, useState, type ReactNode } from "react";
import {
  fetchStockAiAnalysis,
  fetchStockAiHealth,
  type SearxngStatus,
  type StockAiAnalysis,
} from "../../api";
import StockSymbolPicker, { type StockSymbolOption } from "../StockSymbolPicker";
import TimestampLabel from "../TimestampLabel";
import { displaySymbol } from "../../utils/tradingView";

function fmt(v: number | null | undefined, suffix = ""): string {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("en-IN", { maximumFractionDigits: 2 }) + suffix;
}

function retClass(v: number | null | undefined): string {
  if (v === null || v === undefined) return "";
  return v >= 0 ? "stock-ai-pos" : "stock-ai-neg";
}

/** Render the bold segments (**text**) inside one markdown line. */
function inline(line: string, key: number): ReactNode {
  const parts = line.split(/\*\*(.+?)\*\*/g);
  return (
    <span key={key}>
      {parts.map((p, i) => (i % 2 === 1 ? <strong key={i}>{p}</strong> : p))}
    </span>
  );
}

/** Tiny markdown renderer for the report (headings, bullets, paragraphs). */
function renderReport(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let bullets: ReactNode[] = [];

  const flush = () => {
    if (bullets.length) {
      out.push(<ul key={`ul-${out.length}`}>{bullets}</ul>);
      bullets = [];
    }
  };

  text.split("\n").forEach((raw, i) => {
    const line = raw.trim();
    if (!line) {
      flush();
      return;
    }
    if (/^#{1,4}\s/.test(line)) {
      flush();
      out.push(
        <h4 key={i} className="stock-ai-heading">
          {line.replace(/^#{1,4}\s*/, "").replace(/\*\*/g, "")}
        </h4>,
      );
    } else if (/^([-*]|\d+\.)\s/.test(line)) {
      bullets.push(<li key={i}>{inline(line.replace(/^([-*]|\d+\.)\s*/, ""), i)}</li>);
    } else {
      flush();
      out.push(<p key={i}>{inline(line, i)}</p>);
    }
  });
  flush();
  return out;
}

export default function StockAiWidget({ size = "lg" }: { size?: string }) {
  const [picked, setPicked] = useState<StockSymbolOption | null>(null);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<StockAiAnalysis | null>(null);
  const [generatedAt, setGeneratedAt] = useState<Date | null>(null);
  const [useWeb, setUseWeb] = useState(false);
  const [searxng, setSearxng] = useState<SearxngStatus | null>(null);

  useEffect(() => {
    fetchStockAiHealth()
      .then((h) => setSearxng(h.searxng ?? null))
      .catch(() => setSearxng(null));
  }, []);

  const webReady = searxng?.available && searxng?.json;

  async function runAnalysis() {
    if (!picked || loading) return;
    setLoading(true);
    setError(null);
    try {
      // surface a clear message if the lm service isn't running
      await fetchStockAiHealth().catch(() => {
        throw new Error(
          "Stock AI service is not running — start it with: uvicorn app.main:app --port 8010 (from lm/)",
        );
      });
      const res = await fetchStockAiAnalysis(picked.symbol, question.trim() || undefined, useWeb);
      setResult(res);
      setGeneratedAt(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const ps = result?.data.price_summary;
  const profile = result?.data.profile;
  const snapshot = result?.data.snapshot;
  const holdings = result?.data.holdings;

  return (
    <div className="stock-ai-widget">
      <div className="stock-ai-controls">
        <div className="stock-ai-picker">
          <StockSymbolPicker
            value={picked}
            onChange={setPicked}
            disabled={loading}
            placeholder="Pick a stock to analyze…"
          />
        </div>
        <input
          type="text"
          className="stock-ai-question"
          placeholder="Optional question (e.g. Is the recent fall a buying opportunity?)"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && runAnalysis()}
          disabled={loading}
        />
        <button type="button" onClick={runAnalysis} disabled={!picked || loading}>
          {loading ? "Analyzing…" : "🤖 Analyze"}
        </button>
      </div>

      <label
        className="stock-ai-webtoggle"
        title={
          webReady
            ? "Pull live data from the web via SearXNG and let the model use + cite it"
            : searxng?.reason ?? "SearXNG status unknown"
        }
      >
        <input
          type="checkbox"
          checked={useWeb}
          disabled={loading || !webReady}
          onChange={(e) => setUseWeb(e.target.checked)}
        />
        🌐 Use live web search (SearXNG)
        {searxng && !webReady && (
          <span className="stock-ai-web-warn">
            — unavailable: {searxng.reason ?? "not reachable"}
          </span>
        )}
      </label>

      {loading && (
        <div className="widget-loading">
          Crunching prices, fundamentals and news for {picked ? displaySymbol(picked.symbol) : ""}…
          local LLM, can take a minute.
        </div>
      )}
      {error && <div className="widget-error">{error}</div>}
      {!loading && !error && !result && (
        <div className="widget-empty">
          Pick a stock and hit Analyze — the report combines your screener data
          (prices, fundamentals, holdings) with news retrieved from Qdrant,
          written by the local deepseek-r1 model.
        </div>
      )}

      {!loading && result && (
        <div className="stock-ai-result">
          <div className="stock-ai-stats">
            <span className="stock-ai-chip">
              <strong>{displaySymbol(result.symbol)}</strong>{" "}
              {profile?.company_name ?? snapshot?.company_name ?? ""}
            </span>
            {ps && (
              <>
                <span className="stock-ai-chip">₹{fmt(ps.last_close)}</span>
                <span className={`stock-ai-chip ${retClass(ps.return_1m_pct)}`}>
                  1M {fmt(ps.return_1m_pct, "%")}
                </span>
                <span className={`stock-ai-chip ${retClass(ps.return_1y_pct)}`}>
                  1Y {fmt(ps.return_1y_pct, "%")}
                </span>
              </>
            )}
            {snapshot?.pe_ratio != null && (
              <span className="stock-ai-chip">PE {fmt(snapshot.pe_ratio)}</span>
            )}
            {(profile?.market_cap_cr ?? snapshot?.market_cap_cr) != null && (
              <span className="stock-ai-chip">
                MCap {fmt(profile?.market_cap_cr ?? snapshot?.market_cap_cr)} Cr
              </span>
            )}
            {holdings?.promoter_pct != null && (
              <span className="stock-ai-chip">Promoter {fmt(holdings.promoter_pct, "%")}</span>
            )}
          </div>

          {result.web_used && result.web_used.length > 0 && (
            <div className="stock-ai-webnote">
              🌐 Live web search was used — {result.web_used.length} source
              {result.web_used.length > 1 ? "s" : ""} via SearXNG
            </div>
          )}

          <div className="stock-ai-report">{renderReport(result.report)}</div>

          {result.web_used && result.web_used.length > 0 && (
            <details className="stock-ai-details">
              <summary>🌐 Live web sources ({result.web_used.length})</summary>
              {result.web_used.map((w, i) => (
                <div key={i} className="stock-ai-news-item">
                  <a
                    className="stock-ai-news-title stock-ai-web-link"
                    href={w.url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {w.title || w.url}
                  </a>
                  <span className="stock-ai-news-meta">
                    {w.engine}
                    {w.published ? ` · ${w.published}` : ""} · {w.url}
                  </span>
                </div>
              ))}
            </details>
          )}

          {result.news_used.length > 0 && (
            <details className="stock-ai-details">
              <summary>News context used ({result.news_used.length})</summary>
              {result.news_used.map((n, i) => (
                <div key={i} className="stock-ai-news-item">
                  <span className="stock-ai-news-title">
                    [{n.ticker}] {n.title}
                  </span>
                  <span className="stock-ai-news-meta">
                    {n.source} {n.date} · score {n.score}
                  </span>
                </div>
              ))}
            </details>
          )}

          {result.reasoning && size === "lg" && (
            <details className="stock-ai-details">
              <summary>Model reasoning</summary>
              <pre className="stock-ai-reasoning">{result.reasoning}</pre>
            </details>
          )}

          <div className="widget-as-of">
            <TimestampLabel at={generatedAt} label="Generated" />
            <span className="widget-as-of-note"> · local deepseek-r1 · not investment advice</span>
          </div>
        </div>
      )}
    </div>
  );
}
