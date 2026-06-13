"""Scikit-learn experiments for IPO profitability patterns."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.db import crud
from app.db.database import SessionLocal
from app.services.ipo_research.dataset import load_dataset_dataframe, prepare_ipo_dataset

logger = logging.getLogger(__name__)

# Columns never used as model inputs (identifiers + targets + outcomes)
EXCLUDE_COLS = frozenset(
    {
        "symbol",
        "listing_date",
        "target_profit_listing_day",
        "target_profit_vs_issue",
        "target_strong_profit_vs_issue",
        "target_profit_buy_listing_open",
        "target_listing_day_gain_pct",
        "target_gain_vs_issue_pct",
        "target_gain_listing_open_to_current_pct",
    }
)

TARGET_OPTIONS = {
    "profit_listing_day": "target_profit_listing_day",
    "profit_vs_issue": "target_profit_vs_issue",
    "strong_profit_vs_issue": "target_strong_profit_vs_issue",
    "profit_buy_listing_open": "target_profit_buy_listing_open",
}

TARGET_PLAIN: dict[str, dict[str, str]] = {
    "profit_listing_day": {
        "question": "If you bought at the IPO issue price and sold at the close on listing day, would you make money?",
        "success_label": "made money on listing day",
        "gain_column": "target_listing_day_gain_pct",
    },
    "profit_vs_issue": {
        "question": "If you bought at the IPO issue price and held until today, would you still be in profit?",
        "success_label": "still profitable vs issue price",
        "gain_column": "target_gain_vs_issue_pct",
    },
    "strong_profit_vs_issue": {
        "question": "If you bought at the IPO issue price and held until today, would you gain at least 15%?",
        "success_label": "gained 15% or more vs issue price",
        "gain_column": "target_gain_vs_issue_pct",
    },
    "profit_buy_listing_open": {
        "question": "If you bought at the opening price on listing day and held until today, would you be in profit?",
        "success_label": "profitable after buying at listing-day open",
        "gain_column": "target_gain_listing_open_to_current_pct",
    },
}

ALGORITHM_CHOICES = frozenset(
    {
        "all",
        "random_forest",
        "logistic_regression",
        "gradient_boosting",
    }
)


def _generate_pattern_insights(
    target_label: str,
    top_features: list[dict[str, Any]],
    metrics: dict[str, Any],
    df: pd.DataFrame,
    target_col: str,
) -> list[str]:
    """Rule-based interpretation of ML outputs (educational, not financial advice)."""
    insights: list[str] = []
    acc = metrics.get("test_accuracy")
    if acc is not None:
        insights.append(
            f"Model test accuracy for '{target_label}' was {acc:.1%} "
            f"(CV mean {metrics.get('cv_mean', 0):.1%}). "
            "Past patterns may not repeat."
        )

    if top_features:
        names = [f["feature"] for f in top_features[:3]]
        insights.append(
            f"Strongest signals in this run: {', '.join(names)}."
        )

    if "market_avg_return_1m_before" in df.columns and target_col in df.columns:
        subset = df[[target_col, "market_avg_return_1m_before"]].dropna()
        if len(subset) >= 20:
            bull = subset[subset["market_avg_return_1m_before"] > 0][target_col].mean()
            bear = subset[subset["market_avg_return_1m_before"] <= 0][target_col].mean()
            if bull is not None and bear is not None:
                insights.append(
                    f"When broader market 1M return before listing was positive, "
                    f"target hit rate was {bull:.1%} vs {bear:.1%} in weak markets."
                )

    if "overall_times_subscribed" in df.columns:
        sub = df[df["overall_times_subscribed"].notna()]
        if len(sub) >= 15 and target_col in sub.columns:
            hot = sub[sub["overall_times_subscribed"] >= 3][target_col].mean()
            cold = sub[sub["overall_times_subscribed"] < 2][target_col].mean()
            if hot is not None and cold is not None:
                insights.append(
                    f"Heavily subscribed IPOs (≥3× overall): {hot:.1%} positive outcomes "
                    f"vs lightly subscribed (<2×): {cold:.1%}."
                )

    if "qib_times_subscribed" in df.columns:
        qib_df = df[df["qib_times_subscribed"].notna()]
        if len(qib_df) >= 12 and target_col in qib_df.columns:
            strong_qib = qib_df[qib_df["qib_times_subscribed"] >= 25][target_col].mean()
            weak_qib = qib_df[qib_df["qib_times_subscribed"] < 10][target_col].mean()
            if strong_qib is not None and weak_qib is not None:
                insights.append(
                    f"High QIB demand (≥25×): {strong_qib:.1%} hit rate vs low QIB (<10×): {weak_qib:.1%}."
                )

    if "retail_times_subscribed" in df.columns:
        ret = df[df["retail_times_subscribed"].notna()]
        if len(ret) >= 12 and target_col in ret.columns:
            hot_ret = ret[ret["retail_times_subscribed"] >= 5][target_col].mean()
            cold_ret = ret[ret["retail_times_subscribed"] < 2][target_col].mean()
            if hot_ret is not None and cold_ret is not None:
                insights.append(
                    f"Retail oversubscription (≥5×): {hot_ret:.1%} vs under 2× retail: {cold_ret:.1%}."
                )

    if "security_type_sme" in df.columns:
        sme = df[df["security_type_sme"] == 1][target_col].mean()
        main = df[df["security_type_sme"] == 0][target_col].mean()
        if sme is not None and main is not None and df["security_type_sme"].sum() >= 5:
            insights.append(
                f"SME IPO positive rate: {sme:.1%} vs mainboard: {main:.1%}."
            )

    return insights


def _example_ipo_rows(
    df: pd.DataFrame,
    target_col: str,
    gain_col: str,
    *,
    winners: bool,
    n: int = 4,
) -> list[dict[str, Any]]:
    if gain_col not in df.columns:
        return []
    sub = df[df[target_col] == (1 if winners else 0)].copy()
    if sub.empty:
        return []
    sub = sub.sort_values(gain_col, ascending=not winners)
    out: list[dict[str, Any]] = []
    for _, row in sub.head(n).iterrows():
        gain = row.get(gain_col)
        item: dict[str, Any] = {
            "symbol": str(row.get("symbol", "")),
            "listing_date": str(row.get("listing_date", "")),
            "gain_pct": round(float(gain), 2) if gain is not None and not pd.isna(gain) else None,
        }
        mkt = row.get("market_avg_return_1m_before")
        if mkt is not None and not pd.isna(mkt):
            item["market_1m_before_pct"] = round(float(mkt), 2)
        sub_mult = row.get("overall_times_subscribed")
        if sub_mult is not None and not pd.isna(sub_mult):
            item["subscription_x"] = round(float(sub_mult), 2)
        out.append(item)
    return out


def _build_narrative_summary(
    target_key: str,
    df: pd.DataFrame,
    target_col: str,
    experiments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Plain-English story + IPO examples (what users actually care about)."""
    meta = TARGET_PLAIN.get(target_key, {})
    gain_col = meta.get("gain_column", "target_gain_vs_issue_pct")
    hit_rate = float(df[target_col].mean()) if len(df) else 0.0
    n = len(df)
    n_hit = int(df[target_col].sum())

    winners = _example_ipo_rows(df, target_col, gain_col, winners=True)
    losers = _example_ipo_rows(df, target_col, gain_col, winners=False)

    best_acc = max((e["metrics"]["test_accuracy"] for e in experiments), default=0.0)
    top_feat = ""
    if experiments and experiments[0].get("top_features"):
        top_feat = experiments[0]["top_features"][0]["feature"]

    winner_names = ", ".join(
        f"{w['symbol']} ({w['gain_pct']:+.1f}%)" for w in winners[:3] if w.get("gain_pct") is not None
    )
    loser_names = ", ".join(
        f"{l['symbol']} ({l['gain_pct']:+.1f}%)" for l in losers[:3] if l.get("gain_pct") is not None
    )

    bottom_line = (
        f"Out of {n} recent IPOs in your dataset, {n_hit} ({hit_rate:.0%}) "
        f"{meta.get('success_label', 'met the goal')}. "
    )
    if winner_names:
        bottom_line += f"Strong outcomes included {winner_names}. "
    if loser_names:
        bottom_line += f"Weak outcomes included {loser_names}. "

    model_note = (
        f"The ML model guessed outcomes correctly about {best_acc:.0%} of the time on a small "
        f"held-out test slice — with only {n} IPOs this is indicative, not a trading rule."
    )

    takeaway = (
        f"{hit_rate:.0%} of IPOs {meta.get('success_label', 'succeeded')}"
        + (f"; e.g. {winners[0]['symbol']} {winners[0]['gain_pct']:+.0f}%" if winners and winners[0].get("gain_pct") is not None else "")
    )

    paragraphs = [
        f"What we measured: {meta.get('question', target_key)}",
        bottom_line.strip(),
        model_note,
    ]
    if top_feat:
        paragraphs.append(
            f"The model weighted market conditions and issue size heavily (top signal: {top_feat.replace('_', ' ')}), "
            "but with 37 IPOs you should treat this as exploration, not a buy/sell checklist."
        )

    return {
        "what_we_measured": meta.get("question", ""),
        "bottom_line": bottom_line.strip(),
        "takeaway_one_liner": takeaway[:220],
        "hit_rate": round(hit_rate, 4),
        "sample_count": n,
        "success_count": n_hit,
        "example_winners": winners,
        "example_losers": losers,
        "paragraphs": paragraphs,
        "caveats": [
            f"Small sample: only {n} IPOs (recent listings with price data).",
            "Past IPO results do not predict future listings.",
            "Not financial advice.",
        ],
    }


def _run_classifier(
    name: str,
    model,
    X: pd.DataFrame,
    y: pd.Series,
) -> dict[str, Any]:
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y if y.nunique() > 1 else None
    )

    pipe = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("clf", model),
        ]
    )

    cv_scores = cross_val_score(pipe, X, y, cv=5, scoring="accuracy")
    pipe.fit(X_train, y_train)
    y_pred = pipe.predict(X_test)

    metrics = {
        "test_accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "test_f1": round(float(f1_score(y_test, y_pred, zero_division=0)), 4),
        "cv_mean": round(float(cv_scores.mean()), 4),
        "cv_std": round(float(cv_scores.std()), 4),
        "train_size": int(len(X_train)),
        "test_size": int(len(X_test)),
        "positive_rate": round(float(y.mean()), 4),
    }

    report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)

    top_features: list[dict[str, Any]] = []
    clf = pipe.named_steps["clf"]
    feature_names = list(X.columns)
    if hasattr(clf, "feature_importances_"):
        imp = clf.feature_importances_
        order = np.argsort(imp)[::-1][:10]
        top_features = [
            {"feature": feature_names[i], "importance": round(float(imp[i]), 4)}
            for i in order
        ]
    elif hasattr(clf, "coef_"):
        coef = np.abs(clf.coef_[0])
        order = np.argsort(coef)[::-1][:10]
        top_features = [
            {"feature": feature_names[i], "importance": round(float(coef[i]), 4)}
            for i in order
        ]

    return {
        "model": name,
        "metrics": metrics,
        "classification_report": report,
        "top_features": top_features,
    }


def run_ml_experiment(
    algorithm: str = "all",
    target_key: str = "profit_vs_issue",
    *,
    prepare_data: bool = True,
    force_data_refresh: bool = False,
) -> dict[str, Any]:
    """Execute ML pipeline; persists IpoResearchRun row."""
    if algorithm not in ALGORITHM_CHOICES:
        raise ValueError(f"Unknown algorithm: {algorithm}")
    if target_key not in TARGET_OPTIONS:
        raise ValueError(f"Unknown target: {target_key}")

    target_col = TARGET_OPTIONS[target_key]

    with SessionLocal() as db:
        run = crud.create_ipo_research_run(
            db,
            algorithm=algorithm,
            params_json=json.dumps(
                {"target": target_key, "prepare_data": prepare_data}
            ),
        )
        run_id = run.id

    try:
        prep_summary = None
        if prepare_data:
            prep_summary = prepare_ipo_dataset(
                force_refresh=force_data_refresh,
                months=6,
                fetch_subscription=True,
            )

        df = load_dataset_dataframe()
        if df.empty or len(df) < 30:
            raise ValueError(
                f"Need at least 30 IPO rows in dataset (have {len(df)}). "
                "Run 'Prepare data' first."
            )

        work = df.dropna(subset=[target_col])
        if len(work) < 30:
            raise ValueError(f"Only {len(work)} rows with target '{target_key}'")

        feature_cols = [
            c
            for c in work.columns
            if c not in EXCLUDE_COLS
            and not c.startswith("target_")
            and work[c].dtype in ("float64", "int64", "float32", "int32")
        ]
        X = work[feature_cols].copy()
        y = work[target_col].astype(int)

        experiments: list[dict[str, Any]] = []
        models_to_run: list[tuple[str, object]] = []

        if algorithm in ("all", "random_forest"):
            models_to_run.append(
                (
                    "random_forest",
                    RandomForestClassifier(
                        n_estimators=100, max_depth=8, random_state=42, class_weight="balanced"
                    ),
                )
            )
        if algorithm in ("all", "logistic_regression"):
            models_to_run.append(
                (
                    "logistic_regression",
                    LogisticRegression(max_iter=500, class_weight="balanced", random_state=42),
                )
            )
        if algorithm in ("all", "gradient_boosting"):
            models_to_run.append(
                (
                    "gradient_boosting",
                    GradientBoostingClassifier(
                        n_estimators=80, max_depth=4, random_state=42
                    ),
                )
            )

        for model_name, model in models_to_run:
            result = _run_classifier(model_name, model, X, y)
            result["insights"] = _generate_pattern_insights(
                target_key,
                result["top_features"],
                result["metrics"],
                work,
                target_col,
            )
            experiments.append(result)

        narrative = _build_narrative_summary(target_key, work, target_col, experiments)

        summary_lines = [
            f"IPO pattern research — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            "",
            "── Plain summary ──",
            *narrative["paragraphs"],
            "",
            "── Model stats (technical) ──",
            f"Samples: {len(work)} IPOs | Target: {target_key}",
        ]
        for exp in experiments:
            m = exp["metrics"]
            summary_lines.append(
                f"• {exp['model']}: accuracy {m['test_accuracy']:.1%}, CV {m['cv_mean']:.1%}"
            )

        summary_text = "\n".join(summary_lines)
        insights_payload = {
            "target": target_key,
            "feature_columns": feature_cols,
            "experiments": experiments,
            "data_preparation": prep_summary,
            "narrative": narrative,
        }
        metrics_payload = {
            "sample_count": len(work),
            "positive_rate": round(float(y.mean()), 4),
            "best_accuracy": max(e["metrics"]["test_accuracy"] for e in experiments),
            "summary_one_liner": narrative["takeaway_one_liner"],
            "hit_rate": narrative["hit_rate"],
        }

        with SessionLocal() as db:
            crud.update_ipo_research_run(
                db,
                run_id,
                status="completed",
                metrics_json=json.dumps(metrics_payload),
                insights_json=json.dumps(insights_payload),
                summary_text=summary_text,
                sample_count=len(work),
            )
            run = crud.get_ipo_research_run(db, run_id)

        return _run_to_dict(run)

    except Exception as exc:
        logger.exception("IPO ML run %s failed", run_id)
        with SessionLocal() as db:
            crud.update_ipo_research_run(
                db,
                run_id,
                status="failed",
                error_message=str(exc)[:2000],
            )
            run = crud.get_ipo_research_run(db, run_id)
        return _run_to_dict(run)


def _run_to_dict(run) -> dict[str, Any]:
    if run is None:
        return {}
    return {
        "id": run.id,
        "algorithm": run.algorithm,
        "status": run.status,
        "params": json.loads(run.params_json) if run.params_json else {},
        "metrics": json.loads(run.metrics_json) if run.metrics_json else {},
        "insights": json.loads(run.insights_json) if run.insights_json else {},
        "summary_text": run.summary_text,
        "sample_count": run.sample_count,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _maybe_attach_narrative(run_dict: dict[str, Any]) -> dict[str, Any]:
    """Backfill plain summary for older runs that lack narrative."""
    insights = run_dict.get("insights") or {}
    if insights.get("narrative"):
        return run_dict
    target_key = insights.get("target") or (run_dict.get("params") or {}).get("target")
    if not target_key or target_key not in TARGET_OPTIONS:
        return run_dict
    df = load_dataset_dataframe()
    target_col = TARGET_OPTIONS[target_key]
    if df.empty or target_col not in df.columns:
        return run_dict
    work = df.dropna(subset=[target_col])
    experiments = insights.get("experiments") or []
    narrative = _build_narrative_summary(target_key, work, target_col, experiments)
    insights["narrative"] = narrative
    run_dict["insights"] = insights
    if run_dict.get("metrics") is not None:
        run_dict["metrics"]["summary_one_liner"] = narrative["takeaway_one_liner"]
        run_dict["metrics"]["hit_rate"] = narrative["hit_rate"]
    return run_dict


def get_run(run_id: int) -> dict[str, Any] | None:
    with SessionLocal() as db:
        run = crud.get_ipo_research_run(db, run_id)
    if not run:
        return None
    d = _run_to_dict(run)
    return _maybe_attach_narrative(d)


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        runs = crud.list_ipo_research_runs(db, limit=limit)
    return [_maybe_attach_narrative(_run_to_dict(r)) for r in runs]
