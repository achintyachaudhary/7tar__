import { useEffect, useState } from "react";
import { fetchVendors, type FeatureVendor } from "../api";

const KIND_LABEL: Record<string, string> = {
  api: "API",
  scrape: "Scraper",
  lib: "Library",
};

export default function DataSourcesPage() {
  const [features, setFeatures] = useState<FeatureVendor[]>([]);
  const [upstoxConfigured, setUpstoxConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchVendors()
      .then((res) => {
        setFeatures(res.features);
        setUpstoxConfigured(res.upstox_configured);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="page-container data-sources-page">
      <div className="page-header">
        <h1 className="page-title">Data sources</h1>
        <p className="page-subtitle">
          Which vendor powers each feature. Swap one by setting its env override and
          restarting the backend. Upstox token:{" "}
          <strong className={upstoxConfigured ? "positive" : "negative"}>
            {upstoxConfigured ? "configured" : "missing"}
          </strong>
        </p>
      </div>

      {loading && <p className="scan-meta">Loading…</p>}
      {error && <div className="status error">{error}</div>}
      {!loading && !error && (
        <div className="table-wrap">
          <table className="data-sources-table">
            <thead>
              <tr>
                <th>Feature</th>
                <th>Vendor</th>
                <th>Type</th>
                <th>Override</th>
              </tr>
            </thead>
            <tbody>
              {features.map((f) => (
                <tr key={f.capability} className={f.degraded ? "data-source-degraded" : ""}>
                  <td>
                    <div className="data-source-feature">{f.label}</div>
                    <div className="data-source-desc">{f.description}</div>
                    {f.note && <div className="data-source-note">⚠ {f.note}</div>}
                  </td>
                  <td>
                    <span className="data-source-vendor">{f.vendor_label}</span>
                    {f.options.length > 1 && (
                      <div className="data-source-desc">
                        alternatives: {f.options.filter((o) => o !== f.vendor).join(", ")}
                      </div>
                    )}
                  </td>
                  <td>
                    <span className={`data-source-kind data-source-kind-${f.vendor_kind}`}>
                      {KIND_LABEL[f.vendor_kind] ?? f.vendor_kind}
                    </span>
                  </td>
                  <td>
                    <code className="data-source-env">{f.env_override}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
