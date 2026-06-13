import { useEffect, useState } from "react";
import { fetchIpoLlmResearch } from "../api";
import type { IpoLlmFetchStatus } from "../types/ipoResearch";
import type { IpoSubscriptionResearch } from "../types/ipoResearch";
import IpoSubscriptionDisplay from "./IpoSubscriptionDisplay";

interface IpoSubscriptionModalProps {
  symbol: string | null;
  companyName?: string | null;
  fetchStatus: IpoLlmFetchStatus;
  errorMessage?: string | null;
  onClose: () => void;
}

export default function IpoSubscriptionModal({
  symbol,
  companyName,
  fetchStatus,
  errorMessage,
  onClose,
}: IpoSubscriptionModalProps) {
  const [data, setData] = useState<IpoSubscriptionResearch | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!symbol) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [symbol, onClose]);

  useEffect(() => {
    if (!symbol || fetchStatus !== "fetched") {
      setData(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetchIpoLlmResearch(symbol)
      .then((res) => {
        if (!cancelled) setData(res.data);
      })
      .catch(() => {
        if (!cancelled) setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol, fetchStatus]);

  if (!symbol) return null;

  const title = companyName || symbol;

  let body: React.ReactNode;
  if (fetchStatus === "fetching") {
    body = <p className="panel-loading">Fetching subscription data from Gemini…</p>;
  } else if (fetchStatus === "pending") {
    body = (
      <p className="ipo-research-hint">
        Subscription data not fetched yet. Use <strong>Fetch IPO subscription</strong>{" "}
        above to load data for all pending IPOs.
      </p>
    );
  } else if (fetchStatus === "failed") {
    body = (
      <p className="panel-error">
        Fetch failed{errorMessage ? `: ${errorMessage}` : "."}
      </p>
    );
  } else {
    body = (
      <IpoSubscriptionDisplay
        data={data}
        loading={loading}
        emptyMessage="Could not load stored subscription data."
      />
    );
  }

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal-panel ipo-subscription-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="ipo-sub-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal-header">
          <div className="modal-title-wrap">
            <h2 id="ipo-sub-modal-title">{title}</h2>
            <span className="ipo-sub-modal-symbol">{symbol}</span>
          </div>
          <button
            type="button"
            className="modal-close"
            onClick={onClose}
            aria-label="Close"
          >
            ✕
          </button>
        </header>
        <div className="modal-body">
          <section className="ipo-research-panel">{body}</section>
        </div>
      </div>
    </div>
  );
}
