import { useCallback, useState } from "react";
import { fetchIpoIntel } from "../../api";
import { useLiveRefresh } from "../../hooks/useLiveRefresh";
import type { IpoIntelRow } from "../../types/ipoIntel";
import { Link } from "react-router-dom";

function fmtDate(iso: string | null): string {
  if (!iso) return "TBA";
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
  });
}

export default function IpoRadarWidget() {
  const [rows, setRows] = useState<IpoIntelRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetchIpoIntel();
      const live = res.rows
        .filter((r) => r.status === "open" || r.status === "upcoming")
        .sort((a, b) => {
          if (a.status !== b.status) return a.status === "open" ? -1 : 1;
          return (a.open_date ?? "9999").localeCompare(b.open_date ?? "9999");
        });
      setRows(live);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);
  useLiveRefresh(load, { liveMs: 5 * 60_000, closedMs: 15 * 60_000 });

  if (loading) return <div className="widget-loading">Loading IPOs…</div>;
  if (error) return <div className="widget-error">{error}</div>;
  if (rows.length === 0) {
    return (
      <div className="widget-empty">
        No open or upcoming IPOs right now — run a scrape on the{" "}
        <Link to="/ipo-intel">IPO GMP &amp; Subs</Link> page.
      </div>
    );
  }

  return (
    <div className="ipo-radar">
      <ul className="ipo-radar-list">
        {rows.map((r) => (
          <li key={r.name_key} className="ipo-radar-item">
            <div className="ipo-radar-main">
              <span className={`ipo-intel-status ipo-intel-status-${r.status}`}>
                {r.status}
              </span>
              <span className="ipo-radar-name" title={r.display_name}>
                {r.display_name}
                {r.upstox_verified && (
                  <span className="ipo-radar-verified" title="Verified via Upstox catalog">
                    ✓
                  </span>
                )}
              </span>
            </div>
            <div className="ipo-radar-meta">
              <span>{r.ipo_type === "sme" ? "SME" : "Mainboard"}</span>
              {r.price_band && <span>₹{r.price_band}</span>}
              {r.gmp != null && (
                <span className={r.gmp >= 0 ? "pct-pos" : "pct-neg"}>
                  GMP ₹{r.gmp}
                  {r.gmp_pct != null ? ` (${r.gmp_pct >= 0 ? "+" : ""}${r.gmp_pct}%)` : ""}
                </span>
              )}
              {r.sub_total != null && <span>Subs {r.sub_total}×</span>}
              <span className="ipo-radar-dates">
                {fmtDate(r.open_date)} – {fmtDate(r.close_date)}
              </span>
            </div>
          </li>
        ))}
      </ul>
      <div className="widget-as-of">
        <Link to="/ipo-intel" className="ipo-radar-link">
          Full GMP &amp; subscription table →
        </Link>
      </div>
    </div>
  );
}
