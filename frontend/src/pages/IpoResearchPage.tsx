import { useCallback, useEffect, useState } from "react";
import {
  fetchIpoPortfolioSimulation,
  fetchIpoResearchAlgorithms,
  fetchIpoResearchRun,
  fetchIpoResearchRuns,
  fetchIpoResearchDatasetStats,
  prepareIpoResearchDataset,
  startIpoResearchRun,
} from "../api";
import IpoPortfolioSimulationPanel from "../components/IpoPortfolioSimulation";
import type { IpoPortfolioSimulation } from "../types/ipoPortfolio";
import type { IpoResearchRun } from "../types/ipoResearchMl";
import { formatIST } from "../lib/formatTime";

const TARGET_LABELS: Record<string, string> = {
  profit_listing_day: "Profit if bought at issue (listing day)",
  profit_vs_issue: "Profit vs issue price (hold to date)",
  strong_profit_vs_issue: "Strong profit (≥15% vs issue)",
  profit_buy_listing_open: "Profit if bought at listing open",
};

const RESEARCH_MONTHS = 6;

export default function IpoResearchPage() {
  const [stats, setStats] = useState<{
    total_rows: number;
    nse_universe?: number;
    catalog_total?: number;
    with_market_data?: number;
    with_subscription_data?: number;
    subscription_pending?: number;
    no_market_data?: number;
    ml_ready?: number;
    universe_size?: number;
    pending?: number;
    months_back?: number;
    latest_built_at: string | null;
    ready_for_ml: boolean;
  } | null>(null);
  const [runs, setRuns] = useState<IpoResearchRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<IpoResearchRun | null>(null);
  const [algorithms, setAlgorithms] = useState<string[]>(["all"]);
  const [targets, setTargets] = useState<{ id: string; label: string }[]>([]);

  const [algorithm, setAlgorithm] = useState("all");
  const [target, setTarget] = useState("profit_vs_issue");

  const [preparing, setPreparing] = useState(false);
  const [prepareMsg, setPrepareMsg] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [runMsg, setRunMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [portfolio, setPortfolio] = useState<IpoPortfolioSimulation | null>(null);
  const [portfolioLoading, setPortfolioLoading] = useState(true);

  const refresh = useCallback(async () => {
    setPortfolioLoading(true);
    try {
      const [s, r, a, p] = await Promise.all([
        fetchIpoResearchDatasetStats(RESEARCH_MONTHS),
        fetchIpoResearchRuns(),
        fetchIpoResearchAlgorithms(),
        fetchIpoPortfolioSimulation(RESEARCH_MONTHS).catch(() => null),
      ]);
      setStats(s);
      setRuns(r.runs);
      setAlgorithms(a.algorithms);
      setTargets(a.targets);
      setPortfolio(p);
    } catch {
      setStats(null);
      setRuns([]);
      setPortfolio(null);
    } finally {
      setLoading(false);
      setPortfolioLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function handlePrepareAll() {
    setPreparing(true);
    setPrepareMsg("Starting data preparation…");
    let pending = 1;
    let totalSaved = 0;
    let batchNum = 0;
    const maxBatches = 50;
    try {
      while (pending > 0 && batchNum < maxBatches) {
        batchNum += 1;
        const batch = await prepareIpoResearchDataset(false, RESEARCH_MONTHS);
        totalSaved = batch.total_dataset_rows;
        pending = batch.pending_remaining;
        const withPrices = batch.with_market_data ?? 0;
        const withSub = batch.with_subscription_data ?? 0;
        setPrepareMsg(
          `Batch ${batchNum}: ${withSub} with subscription · ${withPrices} with prices · ${totalSaved} ML-ready · ${pending} price pending…`,
        );
      }
      const last = await fetchIpoResearchDatasetStats(RESEARCH_MONTHS).catch(() => null);
      setPrepareMsg(
        pending > 0
          ? `Stopped after ${batchNum} batches. ${last?.catalog_total ?? "?"} in shared DB, ${last?.with_market_data ?? "?"} with prices, ${last?.total_rows ?? totalSaved} ML-ready.`
          : `Done. Shared catalog: ${last?.catalog_total ?? totalSaved} IPOs, ${last?.with_market_data ?? "?"} with Yahoo prices, ${last?.total_rows ?? totalSaved} ready for ML.`,
      );
      await refresh();
    } catch (err) {
      setPrepareMsg(err instanceof Error ? err.message : "Prepare failed");
    } finally {
      setPreparing(false);
    }
  }

  async function handleRunMl() {
    setRunning(true);
    setRunMsg("Running scikit-learn experiments…");
    try {
      const result = await startIpoResearchRun({
        algorithm,
        target,
        prepare_data: false,
      });
      setRunMsg(
        result.status === "completed"
          ? `Run #${result.id} completed.`
          : `Run #${result.id} failed: ${result.error_message}`,
      );
      await refresh();
      if (result.id) {
        const detail = await fetchIpoResearchRun(result.id);
        setSelectedRun(detail);
      }
    } catch (err) {
      setRunMsg(err instanceof Error ? err.message : "ML run failed");
    } finally {
      setRunning(false);
    }
  }

  async function openRun(id: number) {
    try {
      const detail = await fetchIpoResearchRun(id);
      setSelectedRun(detail);
    } catch {
      setSelectedRun(null);
    }
  }

  if (loading) {
    return (
      <div className="page-container">
        <div className="status loading">Loading IPO research…</div>
      </div>
    );
  }

  return (
    <div className="page-container ipo-research-page">
      <h1 className="page-title">IPO Research</h1>
      <p className="page-subtitle meta">
        Pattern discovery using historical NSE IPOs, market indices (NIFTY / BANKNIFTY /
        SENSEX), and scikit-learn. Not financial advice.
      </p>
      <p className="ipo-research-hint" style={{ marginTop: "0.5rem" }}>
        <strong>Prepare data</strong> uses the <strong>same SQLite table as IPO Tracker</strong>{" "}
        (<code>ipo_listings</code>). Step 1: fetch <strong>subscription times</strong> (overall,
        QIB, NII, retail) via Gemini into the same DB as IPO Tracker. Step 2: sync Yahoo prices.
        Step 3: build ML features including subscription demand. Requires{" "}
        <code>GEMINI_API_KEY</code> in Backend/.env for subscription fetch.
      </p>

      <section className="ipo-research-panel">
        <h3>Dataset</h3>
        <p className="meta">
          <strong>{stats?.nse_universe ?? stats?.universe_size ?? 0}</strong> NSE equity IPOs
          (last {stats?.months_back ?? RESEARCH_MONTHS} months)
          {stats?.with_subscription_data != null && (
            <> · <strong>{stats.with_subscription_data}</strong> with subscription data</>
          )}
          {stats?.with_market_data != null && (
            <> · <strong>{stats.with_market_data}</strong> with Yahoo prices</>
          )}
          {stats?.subscription_pending != null && stats.subscription_pending > 0 && (
            <> · {stats.subscription_pending} subscription fetch pending</>
          )}
          {stats?.total_rows != null && (
            <> · <strong>{stats.total_rows}</strong> ML-ready</>
          )}
          {stats?.no_market_data != null && stats.no_market_data > 0 && (
            <> · {stats.no_market_data} no Yahoo data</>
          )}
          {stats?.pending != null && stats.pending > 0 && (
            <> · {stats.pending} awaiting price fetch</>
          )}
          {stats?.latest_built_at && (
            <> · last built {formatIST(stats.latest_built_at)}</>
          )}
          {!stats?.ready_for_ml && (
            <strong> · need ≥30 ready rows</strong>
          )}
        </p>
        <div className="ipo-research-actions">
          <button
            type="button"
            className="refresh-btn"
            disabled={preparing}
            onClick={() => void handlePrepareAll()}
          >
            {preparing ? "Preparing…" : "1. Prepare IPO data (all listings)"}
          </button>
        </div>
        {prepareMsg && <p className="ipo-fetch-toast">{prepareMsg}</p>}
      </section>

      <IpoPortfolioSimulationPanel data={portfolio} loading={portfolioLoading} />

      <section className="ipo-research-panel">
        <h3>Run ML experiment</h3>
        <div className="ipo-research-form">
          <label>
            Algorithm
            <select
              value={algorithm}
              onChange={(e) => setAlgorithm(e.target.value)}
              disabled={running}
            >
              {algorithms.map((a) => (
                <option key={a} value={a}>
                  {a.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </label>
          <label>
            Profit target
            <select
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              disabled={running}
            >
              {targets.map((t) => (
                <option key={t.id} value={t.id}>
                  {TARGET_LABELS[t.id] ?? t.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="refresh-btn"
            disabled={running || !stats?.ready_for_ml}
            onClick={() => void handleRunMl()}
          >
            {running ? "Running…" : "2. Run scikit-learn analysis"}
          </button>
        </div>
        {runMsg && <p className="ipo-fetch-toast">{runMsg}</p>}
      </section>

      <section className="ipo-research-panel">
        <h3>Research runs</h3>
        {runs.length === 0 ? (
          <p className="ipo-research-hint">No runs yet. Prepare data, then run an experiment.</p>
        ) : (
          <table className="ipo-sub-table ipo-runs-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Date</th>
                <th>Algorithm</th>
                <th>Status</th>
                <th>Samples</th>
                <th>Best accuracy</th>
                <th>Insight summary</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr
                  key={run.id}
                  className="clickable-row"
                  onClick={() => void openRun(run.id)}
                >
                  <td>{run.id}</td>
                  <td>
                    {formatIST(run.created_at)}
                  </td>
                  <td>{run.algorithm}</td>
                  <td>
                    <span className={`ipo-status-badge ipo-status-${run.status === "completed" ? "fetched" : run.status === "failed" ? "failed" : "pending"}`}>
                      {run.status}
                    </span>
                  </td>
                  <td>{run.sample_count ?? "—"}</td>
                  <td>
                    {run.metrics?.best_accuracy != null
                      ? `${(run.metrics.best_accuracy * 100).toFixed(1)}%`
                      : "—"}
                  </td>
                  <td className="ipo-insight-summary-cell">
                    {run.metrics?.summary_one_liner ||
                      run.insights?.narrative?.takeaway_one_liner ||
                      "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {selectedRun && (
        <section className="ipo-research-panel ipo-run-detail">
          <div className="ipo-research-header">
            <h3>Run #{selectedRun.id} details</h3>
            <button type="button" className="modal-close" onClick={() => setSelectedRun(null)}>
              ✕
            </button>
          </div>
          {selectedRun.insights?.narrative && (
            <div className="ipo-plain-summary">
              <h4>What this run means</h4>
              <p className="ipo-plain-lead">
                {selectedRun.insights.narrative.what_we_measured}
              </p>
              <p className="ipo-plain-bottom">
                <strong>Bottom line:</strong> {selectedRun.insights.narrative.bottom_line}
              </p>
              {selectedRun.insights.narrative.example_winners.length > 0 && (
                <div className="ipo-examples">
                  <p className="ipo-label">Examples that met the goal</p>
                  <ul>
                    {selectedRun.insights.narrative.example_winners.map((ex) => (
                      <li key={ex.symbol}>
                        <strong>{ex.symbol}</strong> listed {ex.listing_date}
                        {ex.gain_pct != null && ` · ${ex.gain_pct >= 0 ? "+" : ""}${ex.gain_pct}%`}
                        {ex.market_1m_before_pct != null &&
                          ` · market 1M before: ${ex.market_1m_before_pct >= 0 ? "+" : ""}${ex.market_1m_before_pct}%`}
                        {ex.subscription_x != null && ` · subscribed ${ex.subscription_x}×`}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {selectedRun.insights.narrative.example_losers.length > 0 && (
                <div className="ipo-examples">
                  <p className="ipo-label">Examples that did not meet the goal</p>
                  <ul>
                    {selectedRun.insights.narrative.example_losers.map((ex) => (
                      <li key={ex.symbol}>
                        <strong>{ex.symbol}</strong> listed {ex.listing_date}
                        {ex.gain_pct != null && ` · ${ex.gain_pct >= 0 ? "+" : ""}${ex.gain_pct}%`}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <ul className="ipo-caveats">
                {selectedRun.insights.narrative.caveats.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          )}

          {selectedRun.summary_text && (
            <details className="ipo-technical-details">
              <summary>Technical model output</summary>
              <pre className="ipo-run-summary">{selectedRun.summary_text}</pre>
            </details>
          )}
          {selectedRun.error_message && (
            <p className="panel-error">{selectedRun.error_message}</p>
          )}
          {selectedRun.insights?.experiments?.map((exp) => (
            <div key={exp.model} className="ipo-experiment-block">
              <h4>{exp.model.replace(/_/g, " ")}</h4>
              <p className="meta">
                Accuracy {((exp.metrics?.test_accuracy ?? 0) * 100).toFixed(1)}% · CV{" "}
                {((exp.metrics?.cv_mean ?? 0) * 100).toFixed(1)}% · F1{" "}
                {((exp.metrics?.test_f1 ?? 0) * 100).toFixed(1)}%
              </p>
              {exp.top_features?.length > 0 && (
                <>
                  <p className="ipo-label">Top features</p>
                  <ul className="ipo-feature-list">
                    {exp.top_features.slice(0, 8).map((f) => (
                      <li key={f.feature}>
                        <code>{f.feature}</code> — {f.importance.toFixed(4)}
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {exp.insights?.length > 0 && (
                <>
                  <p className="ipo-label">Patterns / insights</p>
                  <ul className="ipo-insight-list">
                    {exp.insights.map((line, i) => (
                      <li key={i}>{line}</li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
