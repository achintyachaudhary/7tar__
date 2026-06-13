import type {
  CategorySubscription,
  IpoSubscriptionResearch,
} from "../types/ipoResearch";

function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v == null) return "—";
  return v.toLocaleString("en-IN", { maximumFractionDigits: digits });
}

function fmtInt(v: number | null | undefined): string {
  if (v == null) return "—";
  return v.toLocaleString("en-IN");
}

interface IpoSubscriptionDisplayProps {
  data: IpoSubscriptionResearch | null;
  loading?: boolean;
  error?: string | null;
  emptyMessage?: string;
}

export default function IpoSubscriptionDisplay({
  data,
  loading = false,
  error = null,
  emptyMessage = "No subscription data available.",
}: IpoSubscriptionDisplayProps) {
  if (loading) {
    return <p className="panel-loading">Loading subscription data…</p>;
  }

  if (error) {
    return <p className="panel-error">{error}</p>;
  }

  if (!data) {
    return <p className="ipo-research-hint">{emptyMessage}</p>;
  }

  const cats = data.subscription_summary.category_breakdown;
  const categoryRows: { key: string; label: string; sub?: CategorySubscription | null }[] = [
    { key: "qib", label: "QIB", sub: cats?.qualified_institutional_buyers_qib },
    { key: "nii", label: "NII", sub: cats?.non_institutional_investors_nii },
    { key: "rii", label: "Retail (RII)", sub: cats?.retail_individual_investors_rii },
    { key: "emp", label: "Employee", sub: cats?.employee_reservation },
  ];

  return (
    <div className="ipo-research-body">
      <p className="ipo-research-company">
        <strong>{data.company_name}</strong> ({data.ticker_symbol})
      </p>
      <div className="ipo-research-grid">
        <div>
          <span className="ipo-label">Bidding</span>
          <span>
            {data.bidding_period.open_date || "—"} →{" "}
            {data.bidding_period.close_date || "—"}
          </span>
        </div>
        <div>
          <span className="ipo-label">Price band</span>
          <span>
            ₹{fmtNum(data.pricing.price_band_inr.floor)} – ₹
            {fmtNum(data.pricing.price_band_inr.cap)}
          </span>
        </div>
        <div>
          <span className="ipo-label">Issue price</span>
          <span>₹{fmtNum(data.pricing.final_issue_price_inr)}</span>
        </div>
        <div>
          <span className="ipo-label">Issue type</span>
          <span>{data.issue_details.issue_type || "—"}</span>
        </div>
        <div>
          <span className="ipo-label">Issue size</span>
          <span>
            {data.issue_details.total_issue_size_crores_inr != null
              ? `₹${fmtNum(data.issue_details.total_issue_size_crores_inr)} Cr`
              : "—"}
          </span>
        </div>
        <div>
          <span className="ipo-label">Overall subscribed</span>
          <span className="ipo-highlight">
            {fmtNum(data.subscription_summary.overall_times_subscribed)}×
          </span>
        </div>
      </div>

      <table className="ipo-sub-table">
        <thead>
          <tr>
            <th>Category</th>
            <th>Shares offered</th>
            <th>Times subscribed</th>
          </tr>
        </thead>
        <tbody>
          {categoryRows.map(({ key, label, sub }) => (
            <tr key={key}>
              <td>{label}</td>
              <td>{fmtInt(sub?.shares_offered)}</td>
              <td>{fmtNum(sub?.times_subscribed)}×</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
