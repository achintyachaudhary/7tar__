import { useEffect, useState } from "react";
import { fetchIpos } from "../../api";
import type { IpoListing } from "../../types";
import TimestampLabel from "../TimestampLabel";

interface Props {
  size: "sm" | "md" | "lg";
}

const LIMIT_MAP = { sm: 4, md: 7, lg: 12 };

export default function RecentIPOsWidget({ size }: Props) {
  const [ipos, setIpos] = useState<IpoListing[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);
  const [scannedAt, setScannedAt] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    fetchIpos(2)
      .then((d) => {
        setIpos(d.results.slice(0, LIMIT_MAP[size]));
        setScannedAt(d.scanned_at ?? null);
        setFetchedAt(new Date());
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [size]);

  if (loading) return <div className="widget-loading">Loading…</div>;
  if (error) return <div className="widget-error">{error}</div>;
  if (!ipos.length) return <div className="widget-empty">No recent IPOs</div>;

  return (
    <div className="mini-list">
      {ipos.map((ipo) => (
        <div key={ipo.symbol} className="mini-row">
          <span className="mini-symbol">{ipo.symbol}</span>
          <span className="mini-price" style={{ fontSize: "0.75rem", color: "var(--muted)" }}>
            {ipo.listing_date_display || ipo.listing_date}
          </span>
          <span
            className={`mini-chg ${ipo.gain_vs_issue_pct != null && ipo.gain_vs_issue_pct >= 0 ? "pct-pos" : "pct-neg"}`}
          >
            {ipo.gain_vs_issue_pct != null
              ? `${ipo.gain_vs_issue_pct > 0 ? "+" : ""}${ipo.gain_vs_issue_pct.toFixed(1)}%`
              : "—"}
          </span>
        </div>
      ))}
      <div className="widget-as-of">
        <TimestampLabel at={scannedAt ?? fetchedAt} label={scannedAt ? "Scanned" : "Fetched"} />
      </div>
    </div>
  );
}
