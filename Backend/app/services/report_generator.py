"""End-of-Day insight report generator.

Builds a comprehensive HTML report showing:
- Which screener contributed each candidate/trade
- Open trades with P/L
- Closed trades with P/L
- Strategy comparison
- Market summary

Auto-triggered at 3:45 PM IST via the live trading tick loop,
and manually via POST /api/live-trades/send-report.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, time, timezone
from typing import Any

from app.db import crud
from app.db.database import SessionLocal
from app.services import notifier, stockrelay

logger = logging.getLogger(__name__)

IST_OFFSET_HOURS = 5.5
EOD_REPORT_TIME = time(15, 45)  # 3:45 PM IST

_last_report_date: str | None = None


def should_send_eod_report() -> bool:
    """Check if we should auto-send the EOD report (once per day at 3:45 PM IST)."""
    global _last_report_date
    now_utc = datetime.now(timezone.utc)
    from zoneinfo import ZoneInfo
    now_ist = now_utc.astimezone(ZoneInfo("Asia/Kolkata"))
    today_str = now_ist.strftime("%Y-%m-%d")

    if _last_report_date == today_str:
        return False

    if now_ist.weekday() >= 5:
        return False

    return now_ist.time() >= EOD_REPORT_TIME


def mark_report_sent() -> None:
    global _last_report_date
    now_utc = datetime.now(timezone.utc)
    from zoneinfo import ZoneInfo
    now_ist = now_utc.astimezone(ZoneInfo("Asia/Kolkata"))
    _last_report_date = now_ist.strftime("%Y-%m-%d")


def generate_eod_report() -> dict[str, Any]:
    """Build the comprehensive EOD insight report data."""
    with SessionLocal() as db:
        from app.db.models import LiveTradeCandidate

        candidates = [
            _candidate_dict(c)
            for c in db.query(LiveTradeCandidate).all()
        ]
        open_trades = crud.list_live_trades(db, status="open")
        all_trades = crud.list_live_trades(db, status="all")
        state = crud.get_live_trading_state(db)
        summary = _build_strategy_summary(all_trades)

        # Group by source
        candidates_by_source = defaultdict(list)
        for c in candidates:
            candidates_by_source[c.get("source", "unknown")].append(c)

        trades_by_source = defaultdict(list)
        for t in all_trades:
            trades_by_source[t.get("source", "unknown")].append(t)

    closed_trades = [t for t in all_trades if t.get("status") == "closed"]
    total_pnl = sum(t.get("pnl_abs", 0) or 0 for t in closed_trades)
    win_count = sum(1 for t in closed_trades if (t.get("pnl_abs") or 0) > 0)
    win_rate = round(win_count / len(closed_trades) * 100, 1) if closed_trades else 0

    return {
        "state": state,
        "candidates": candidates,
        "candidates_by_source": dict(candidates_by_source),
        "open_trades": open_trades,
        "closed_trades": closed_trades,
        "trades_by_source": dict(trades_by_source),
        "summary": summary,
        "total_pnl": total_pnl,
        "win_rate": win_rate,
        "total_trades": len(all_trades),
        "open_count": len(open_trades),
        "closed_count": len(closed_trades),
    }


def send_eod_report() -> dict[str, Any]:
    """Generate and email the EOD report."""
    import json

    from app.services.job_manager import SCAN_REGISTRY
    from app.services.scan_config import export_all_profiles

    report = generate_eod_report()
    html = _build_html(report)

    with SessionLocal() as db:
        cache_rows = []
        for scan_type in SCAN_REGISTRY:
            cached = crud.get_scan_result_cache(db, scan_type)
            if cached and cached.get("last_scanned_at"):
                cache_rows.append(cached)
    profiles_bundle = export_all_profiles(cache_rows)
    if profiles_bundle.get("profiles"):
        html += (
            "<h3 style='margin-top:24px'>Scanner filter profiles (JSON)</h3>"
            "<p style='color:#64748b;font-size:13px'>Import this JSON on another machine "
            "via Scan Profiles to replay the same filters.</p>"
            f"<pre style='font-size:11px;overflow:auto;max-height:360px;"
            f"background:#f8fafc;padding:12px;border-radius:8px'>"
            f"{json.dumps(profiles_bundle, indent=2)}</pre>"
        )

    subject = _build_subject(report)

    sent = notifier.send_email(subject, html)
    mark_report_sent()

    relay_sent = False
    try:
        relay_sent = stockrelay.push_eod_from_portfolio()
    except Exception:
        logger.exception("StockRelay EOD push failed")

    return {
        "sent": sent,
        "relay_sent": relay_sent,
        "message": "EOD report sent successfully" if sent else "Failed to send report (check RESEND_API_KEY)",
        "open_trades": report["open_count"],
        "closed_trades": report["closed_count"],
        "total_pnl": report["total_pnl"],
    }


def _candidate_dict(c) -> dict:
    return {
        "symbol": c.symbol,
        "source": c.source,
        "status": c.status,
        "company_name": c.company_name,
        "resistance": c.resistance,
        "last_price": c.last_price,
        "volume_confirmed": c.volume_confirmed,
        "added_at": c.added_at.isoformat() if c.added_at else None,
    }


def _build_strategy_summary(trades: list[dict]) -> dict:
    closed = [t for t in trades if t.get("status") == "closed"]
    if not closed:
        return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0, "total_pnl": 0, "avg_pnl_pct": 0}

    wins = [t for t in closed if (t.get("pnl_abs") or 0) > 0]
    losses = [t for t in closed if (t.get("pnl_abs") or 0) <= 0]
    total_pnl = sum(t.get("pnl_abs", 0) or 0 for t in closed)
    avg_pnl = sum(t.get("pnl_pct", 0) or 0 for t in closed) / len(closed)

    return {
        "total": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(closed) * 100, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl_pct": round(avg_pnl, 2),
    }


def _fmt(value: float | None, prefix: str = "") -> str:
    if value is None:
        return "-"
    return f"{prefix}{value:,.2f}"


SOURCE_LABELS = {
    "brst": "Year Breakout",
    "multi_year": "Multi-Year Breakout",
    "golden": "Golden Stocks",
    "weekly": "Weekly Stocks",
    "darvas": "Darvas Box",
    "mean_reversion": "Mean Reversion",
    "vol_squeeze": "Volatility Squeeze",
    "volume_surge": "Volume Surge",
}


def _build_subject(report: dict) -> str:
    from zoneinfo import ZoneInfo
    now_ist = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata"))
    date_str = now_ist.strftime("%d %b %Y")
    pnl = report["total_pnl"]
    pnl_str = f"₹{pnl:+,.0f}" if pnl else "₹0"
    return f"[EOD Report] {date_str} — {report['open_count']} Open, {report['closed_count']} Closed, P/L {pnl_str}"


def _build_html(report: dict) -> str:
    from zoneinfo import ZoneInfo
    now_ist = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata"))

    sections = []

    # Header
    sections.append(f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;max-width:700px;margin:0 auto;">
    <h1 style="color:#1e293b;border-bottom:2px solid #3b82f6;padding-bottom:8px;">
        End-of-Day Insight Report
    </h1>
    <p style="color:#64748b;margin:4px 0 20px;">
        {now_ist.strftime("%A, %d %B %Y %I:%M %p IST")}
    </p>
    """)

    # Summary cards
    summary = report["summary"]
    sections.append(f"""
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px;">
        <div style="background:#f0f9ff;padding:12px 16px;border-radius:8px;flex:1;min-width:120px;">
            <div style="color:#64748b;font-size:12px;">Open Trades</div>
            <div style="font-size:24px;font-weight:700;color:#1e293b;">{report['open_count']}</div>
        </div>
        <div style="background:#f0fdf4;padding:12px 16px;border-radius:8px;flex:1;min-width:120px;">
            <div style="color:#64748b;font-size:12px;">Closed Trades</div>
            <div style="font-size:24px;font-weight:700;color:#1e293b;">{report['closed_count']}</div>
        </div>
        <div style="background:{'#f0fdf4' if report['total_pnl'] >= 0 else '#fef2f2'};padding:12px 16px;border-radius:8px;flex:1;min-width:120px;">
            <div style="color:#64748b;font-size:12px;">Total P/L</div>
            <div style="font-size:24px;font-weight:700;color:{'#16a34a' if report['total_pnl'] >= 0 else '#dc2626'};">
                ₹{report['total_pnl']:+,.0f}
            </div>
        </div>
        <div style="background:#fefce8;padding:12px 16px;border-radius:8px;flex:1;min-width:120px;">
            <div style="color:#64748b;font-size:12px;">Win Rate</div>
            <div style="font-size:24px;font-weight:700;color:#1e293b;">{report['win_rate']}%</div>
        </div>
    </div>
    """)

    # Screener contributions
    sections.append("<h2 style='color:#1e293b;margin:20px 0 8px;'>Screener Contributions</h2>")
    for source, cands in report.get("candidates_by_source", {}).items():
        label = SOURCE_LABELS.get(source, source)
        trades_from = report.get("trades_by_source", {}).get(source, [])
        sections.append(f"""
        <div style="margin-bottom:16px;padding:12px;background:#f8fafc;border-radius:8px;border-left:4px solid #3b82f6;">
            <h3 style="margin:0 0 4px;color:#1e293b;">{label}</h3>
            <p style="margin:0;color:#64748b;font-size:13px;">
                {len(cands)} candidates · {len(trades_from)} trades generated
            </p>
        </div>
        """)

    # Open trades table
    open_trades = report["open_trades"]
    if open_trades:
        sections.append("<h2 style='color:#1e293b;margin:20px 0 8px;'>Open Trades</h2>")
        rows = ""
        for t in open_trades:
            pnl = ((t.get("last_price", 0) or 0) - (t.get("entry_price", 0))) * (t.get("qty", 0) or 0)
            pnl_color = "#16a34a" if pnl >= 0 else "#dc2626"
            rows += f"""
            <tr>
                <td style="padding:6px 8px;">{t.get('symbol', '').replace('.NS', '')}</td>
                <td style="padding:6px 8px;">₹{t.get('entry_price', 0):,.2f}</td>
                <td style="padding:6px 8px;">₹{(t.get('last_price') or 0):,.2f}</td>
                <td style="padding:6px 8px;">₹{(t.get('target_price') or 0):,.2f}</td>
                <td style="padding:6px 8px;color:{pnl_color};font-weight:600;">₹{pnl:+,.0f}</td>
                <td style="padding:6px 8px;color:#64748b;font-size:12px;">{SOURCE_LABELS.get(t.get('source', ''), t.get('source', ''))}</td>
            </tr>
            """
        sections.append(f"""
        <table style="border-collapse:collapse;width:100%;font-size:13px;">
        <tr style="background:#f1f5f9;">
            <th align="left" style="padding:6px 8px;">Symbol</th>
            <th align="right" style="padding:6px 8px;">Entry</th>
            <th align="right" style="padding:6px 8px;">Current</th>
            <th align="right" style="padding:6px 8px;">Target</th>
            <th align="right" style="padding:6px 8px;">Unrealized P/L</th>
            <th align="left" style="padding:6px 8px;">Source</th>
        </tr>
        {rows}
        </table>
        """)

    # Closed trades table
    closed_trades = report["closed_trades"]
    if closed_trades:
        sections.append("<h2 style='color:#1e293b;margin:20px 0 8px;'>Closed Trades</h2>")
        rows = ""
        for t in closed_trades[-10:]:
            pnl_color = "#16a34a" if (t.get("pnl_abs") or 0) >= 0 else "#dc2626"
            rows += f"""
            <tr>
                <td style="padding:6px 8px;">{t.get('symbol', '').replace('.NS', '')}</td>
                <td style="padding:6px 8px;">₹{t.get('entry_price', 0):,.2f}</td>
                <td style="padding:6px 8px;">₹{(t.get('exit_price') or 0):,.2f}</td>
                <td style="padding:6px 8px;">{t.get('exit_reason', '-')}</td>
                <td style="padding:6px 8px;color:{pnl_color};font-weight:600;">
                    ₹{(t.get('pnl_abs') or 0):+,.0f} ({(t.get('pnl_pct') or 0):+.1f}%)
                </td>
                <td style="padding:6px 8px;color:#64748b;">{t.get('days_held', '-')}d</td>
            </tr>
            """
        if len(closed_trades) > 10:
            rows += f'<tr><td colspan="6" style="color:#64748b;padding:6px 8px;">…and {len(closed_trades) - 10} more</td></tr>'
        sections.append(f"""
        <table style="border-collapse:collapse;width:100%;font-size:13px;">
        <tr style="background:#f1f5f9;">
            <th align="left" style="padding:6px 8px;">Symbol</th>
            <th align="right" style="padding:6px 8px;">Entry</th>
            <th align="right" style="padding:6px 8px;">Exit</th>
            <th align="left" style="padding:6px 8px;">Reason</th>
            <th align="right" style="padding:6px 8px;">P/L</th>
            <th align="right" style="padding:6px 8px;">Days</th>
        </tr>
        {rows}
        </table>
        """)

    # Footer
    sections.append("""
    <p style="color:#94a3b8;font-size:11px;margin-top:24px;border-top:1px solid #e2e8f0;padding-top:12px;">
        Paper trading only — no real orders placed. Generated automatically by the live trading engine.
    </p>
    </div>
    """)

    return "\n".join(sections)
