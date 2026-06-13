"""Email alerts for the live-trading engine, sent via the Resend HTTP API.

Configuration (read from the environment / Backend/.env):
- RESEND_API_KEY:        Resend API key.
- LIVE_TRADE_ALERT_EMAIL: recipient (default achintyac77@gmail.com).
- LIVE_TRADE_FROM_EMAIL:  sender (default onboarding@resend.dev).

Note: Resend only delivers to arbitrary inboxes from a verified domain. The
default onboarding@resend.dev sender reliably reaches only your own Resend
account email; verify a domain for guaranteed Gmail delivery.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_RESEND_ENDPOINT = "https://api.resend.com/emails"
_DEFAULT_FROM = "onboarding@resend.dev"
_DEFAULT_TO = "achintyac77@gmail.com"
_BACKEND_ENV = Path(__file__).resolve().parents[2] / ".env"
_EMAIL_NOTIFICATIONS_PREF = "email_notifications"


def _reload_env() -> None:
    """Re-read Backend/.env so key changes apply without a full process restart."""
    load_dotenv(_BACKEND_ENV, override=True)


def _config() -> tuple[str | None, str, str]:
    _reload_env()
    api_key = (os.environ.get("RESEND_API_KEY") or "").strip() or None
    from_email = (os.environ.get("LIVE_TRADE_FROM_EMAIL") or _DEFAULT_FROM).strip()
    to_email = (os.environ.get("LIVE_TRADE_ALERT_EMAIL") or _DEFAULT_TO).strip()
    return api_key, from_email, to_email


def _email_notifications_enabled() -> bool:
    """Read UI preference from user_preferences (default: enabled)."""
    try:
        from app.db import crud
        from app.db.database import SessionLocal

        with SessionLocal() as db:
            val = crud.get_pref(db, _EMAIL_NOTIFICATIONS_PREF)
        if val is None:
            return True
        return val.strip().lower() not in ("0", "false", "no", "off")
    except Exception:
        logger.debug("Could not read email_notifications preference; defaulting to enabled")
        return True


def send_email(subject: str, html: str) -> bool:
    """Send an alert email. Returns True on success; never raises."""
    if not _email_notifications_enabled():
        logger.info("Email notifications disabled in UI; skipping '%s'", subject)
        return False

    api_key, from_email, to_email = _config()
    if not api_key:
        logger.warning("RESEND_API_KEY not set; skipping email '%s'", subject)
        return False

    # Debug: log the key in use (requested for Resend troubleshooting).
    logger.info(
        "Resend send '%s' | key=%s | from=%s | to=%s",
        subject,
        api_key,
        from_email,
        to_email,
    )

    try:
        resp = requests.post(
            _RESEND_ENDPOINT,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": from_email,
                "to": [to_email],
                "subject": subject,
                "html": html,
            },
            timeout=15,
        )
    except Exception:
        logger.exception("Resend request failed for '%s'", subject)
        return False

    if resp.status_code >= 400:
        logger.warning(
            "Resend rejected email '%s' (%s): %s", subject, resp.status_code, resp.text[:300]
        )
        return False

    logger.info("Sent live-trade email: %s", subject)
    return True


def _fmt(value: float | None, prefix: str = "") -> str:
    if value is None:
        return "-"
    return f"{prefix}{value:,.2f}"


def _wrap(title: str, rows: list[tuple[str, str]], footer: str = "") -> str:
    cells = "".join(
        f"<tr><td style='padding:4px 12px 4px 0;color:#64748b'>{k}</td>"
        f"<td style='padding:4px 0;font-weight:600'>{v}</td></tr>"
        for k, v in rows
    )
    return (
        f"<div style='font-family:Segoe UI,Arial,sans-serif;max-width:520px'>"
        f"<h2 style='margin:0 0 12px'>{title}</h2>"
        f"<table style='border-collapse:collapse;font-size:14px'>{cells}</table>"
        f"{('<p style=\"color:#64748b;font-size:13px;margin-top:14px\">' + footer + '</p>') if footer else ''}"
        f"</div>"
    )


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


def notify_candidates_bulk(candidates: list[dict]) -> bool:
    """Single consolidated email after a bulk sync adds multiple candidates."""
    if not candidates:
        return False

    rows_html = ""
    for c in candidates[:80]:
        sym = (c.get("symbol") or "").replace(".NS", "")
        src = SOURCE_LABELS.get(c.get("source", ""), c.get("source", ""))
        entry = c.get("entry_point") or f"Cross above {_fmt(c.get('resistance'), 'Rs.')}"
        rows_html += (
            f"<tr><td style='padding:6px 8px'>{sym}</td>"
            f"<td style='padding:6px 8px'>{src}</td>"
            f"<td style='padding:6px 8px'>{entry}</td>"
            f"<td style='padding:6px 8px'>{_fmt(c.get('target_price'), 'Rs.')}</td>"
            f"<td style='padding:6px 8px'>{_fmt(c.get('stop_price'), 'Rs.')}</td></tr>"
        )
    if len(candidates) > 80:
        rows_html += (
            f"<tr><td colspan='5' style='padding:6px 8px;color:#64748b'>"
            f"…and {len(candidates) - 80} more in the app</td></tr>"
        )

    subject = f"[Live Trades] {len(candidates)} new candidate(s) from screener sync"
    html = (
        f"<div style='font-family:Segoe UI,Arial,sans-serif;max-width:640px'>"
        f"<h2 style='margin:0 0 12px'>Screener sync — {len(candidates)} new candidates</h2>"
        f"<p style='color:#64748b;font-size:14px;margin:0 0 16px'>"
        f"Stocks below were added to the live-trading watchlist. "
        f"Entry triggers when price breaks resistance with volume confirmation (breakout screeners) "
        f"or momentum rules per screener.</p>"
        f"<table style='border-collapse:collapse;font-size:13px;width:100%'>"
        f"<tr style='background:#f1f5f9'>"
        f"<th align='left'>Symbol</th><th>Screener</th><th>Entry</th><th>Target</th><th>Stop</th></tr>"
        f"{rows_html}</table>"
        f"<p style='color:#64748b;font-size:12px;margin-top:16px'>"
        f"Open Live Trades in the app for full rationale per stock.</p></div>"
    )
    return send_email(subject, html)


def notify_candidate_added(candidate: dict) -> bool:
    """Email when a stock is added to the live-trading potential list."""
    source = SOURCE_LABELS.get(candidate.get("source", ""), candidate.get("source", ""))
    subject = f"[Live Trades] Watching {candidate['symbol']} ({source})"
    html = _wrap(
        f"New candidate: {candidate['symbol']}",
        [
            ("Source", source),
            ("Resistance", _fmt(candidate.get("resistance"), "Rs.")),
            ("Planned entry", f"Cross above {_fmt(candidate.get('resistance'), 'Rs.')} with volume confirmation"),
            ("Target", _fmt(candidate.get("target_price"), "Rs.")),
            ("Stop", _fmt(candidate.get("stop_price"), "Rs.")),
            ("Volume", f"{candidate.get('volume_ratio') or '-'}x 50-day avg"),
        ],
        footer=candidate.get("rationale") or "",
    )
    return send_email(subject, html)


def notify_trade_entered(trade: dict) -> bool:
    subject = f"[Live Trades] ENTERED {trade['symbol']} @ Rs.{trade['entry_price']:,.2f}"
    html = _wrap(
        f"Entered trade: {trade['symbol']}",
        [
            ("Strategy", trade.get("strategy", "")),
            ("Entry", _fmt(trade.get("entry_price"), "Rs.")),
            ("Resistance broken", _fmt(trade.get("resistance"), "Rs.")),
            ("Target", _fmt(trade.get("target_price"), "Rs.")),
            ("Stop", _fmt(trade.get("stop_price"), "Rs.")),
            ("Quantity", _fmt(trade.get("qty"))),
            ("Notional", _fmt(trade.get("notional"), "Rs.")),
        ],
        footer=trade.get("rationale") or "",
    )
    return send_email(subject, html)


def notify_trade_exited(trade: dict) -> bool:
    pnl_pct = trade.get("pnl_pct")
    sign = "PROFIT" if (pnl_pct or 0) >= 0 else "LOSS"
    subject = (
        f"[Live Trades] EXITED {trade['symbol']} @ Rs.{(trade.get('exit_price') or 0):,.2f} "
        f"({sign} {pnl_pct:+.2f}%)" if pnl_pct is not None else f"[Live Trades] EXITED {trade['symbol']}"
    )
    html = _wrap(
        f"Closed trade: {trade['symbol']}",
        [
            ("Reason", trade.get("exit_reason", "")),
            ("Entry", _fmt(trade.get("entry_price"), "Rs.")),
            ("Exit", _fmt(trade.get("exit_price"), "Rs.")),
            ("P&L", f"{_fmt(trade.get('pnl_abs'), 'Rs.')} ({pnl_pct:+.2f}%)" if pnl_pct is not None else "-"),
            ("Days held", str(trade.get("days_held") or "-")),
        ],
    )
    return send_email(subject, html)


def notify_price_alert(alert: dict[str, Any]) -> bool:
    """Email when a user price alert is triggered."""
    sym = (alert.get("symbol") or "").replace(".NS", "")
    direction = alert.get("direction", "above")
    target = alert.get("target_price")
    triggered = alert.get("triggered_price")
    subject = f"[Price Alert] {sym} hit Rs.{triggered:,.2f} ({direction} Rs.{target:,.2f})"
    html = _wrap(
        f"Price alert triggered: {sym}",
        [
            ("Symbol", sym),
            ("Condition", f"Price goes {direction} Rs.{target:,.2f}"),
            ("Triggered at", _fmt(triggered, "Rs.")),
            ("Company", alert.get("company_name") or "-"),
        ],
        footer=alert.get("note") or "",
    )
    return send_email(subject, html)


def notify_client_report(report: dict[str, Any]) -> bool:
    """Email a full live-trading status snapshot to the client."""
    mode = report.get("mode_label", "-")
    market = "Open" if report.get("market_open") else "Closed"
    candidates = report.get("candidates") or []
    open_trades = report.get("open_trades") or []
    closed_trades = report.get("closed_trades") or []
    summary = report.get("summary") or {}
    strategies = summary.get("strategies") or []

    cand_rows = "".join(
        f"<tr><td>{c.get('symbol', '').replace('.NS', '')}</td>"
        f"<td>{c.get('status', '-')}</td>"
        f"<td>Rs.{c.get('resistance', 0):,.2f}</td>"
        f"<td>{'Rs.' + format(c.get('last_price'), ',.2f') if c.get('last_price') else '-'}</td></tr>"
        for c in candidates[:15]
    )
    if len(candidates) > 15:
        cand_rows += f"<tr><td colspan='4' style='color:#64748b'>…and {len(candidates) - 15} more</td></tr>"

    if open_trades:
        open_rows = "".join(
            f"<tr><td>{t.get('symbol', '').replace('.NS', '')}</td>"
            f"<td>Rs.{t.get('entry_price', 0):,.2f}</td>"
            f"<td>{'Rs.' + format(t.get('last_price'), ',.2f') if t.get('last_price') else '-'}</td>"
            f"<td>{'Rs.' + format(t.get('target_price'), ',.2f') if t.get('target_price') else '-'}</td></tr>"
            for t in open_trades
        )
    else:
        open_rows = "<tr><td colspan='4' style='color:#64748b'>No open trades</td></tr>"

    strat_rows = "".join(
        f"<tr><td>{s.get('label', '-')}{' (active)' if s.get('executed') else ''}</td>"
        f"<td>{s.get('trades', 0)}</td>"
        f"<td>{s.get('win_rate', 0)}%</td>"
        f"<td>{s.get('total_pnl_abs', 0):+,.0f}</td></tr>"
        for s in strategies
    )

    subject = f"[Live Trades] Client Report — {mode} · NSE {market}"
    html = (
        f"<div style='font-family:Segoe UI,Arial,sans-serif;max-width:640px'>"
        f"<h2 style='margin:0 0 8px'>Live Trades — Client Status Report</h2>"
        f"<p style='color:#64748b;margin:0 0 16px'>Snapshot as of engine tick {report.get('last_tick_at', 'now')}</p>"
        f"<table style='border-collapse:collapse;font-size:14px;margin-bottom:20px'>"
        f"<tr><td style='padding:4px 12px 4px 0;color:#64748b'>Active mode</td><td><strong>{mode}</strong></td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;color:#64748b'>NSE session</td><td>{market}</td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;color:#64748b'>Strategy</td><td>Smart Swing (paper)</td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;color:#64748b'>Capital / trade</td>"
        f"<td>Rs.{(report.get('capital_per_trade') or 0):,.0f}</td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;color:#64748b'>Last engine tick</td><td>{report.get('last_tick_at', '-')}</td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;color:#64748b'>Last live data</td><td>{report.get('last_data_at', '-')}</td></tr>"
        f"</table>"
        f"<h3 style='margin:16px 0 8px'>Candidates ({len(candidates)})</h3>"
        f"<table style='border-collapse:collapse;font-size:13px;width:100%'>"
        f"<tr style='background:#f1f5f9'><th align='left'>Symbol</th><th>Status</th><th>Resistance</th><th>Last</th></tr>"
        f"{cand_rows or '<tr><td colspan=4>No candidates</td></tr>'}"
        f"</table>"
        f"<h3 style='margin:16px 0 8px'>Open trades ({len(open_trades)})</h3>"
        f"<table style='border-collapse:collapse;font-size:13px;width:100%'>"
        f"<tr style='background:#f1f5f9'><th align='left'>Symbol</th><th>Entry</th><th>Last</th><th>Target</th></tr>"
        f"{open_rows}"
        f"</table>"
        f"<h3 style='margin:16px 0 8px'>Strategy comparison</h3>"
        f"<table style='border-collapse:collapse;font-size:13px;width:100%'>"
        f"<tr style='background:#f1f5f9'><th align='left'>Strategy</th><th>Trades</th><th>Win%</th><th>P&L Rs.</th></tr>"
        f"{strat_rows or '<tr><td colspan=4>No data yet</td></tr>'}"
        f"</table>"
        f"<p style='color:#64748b;font-size:12px;margin-top:20px'>Paper trading only — no real orders placed. "
        f"Closed trades: {len(closed_trades)}.</p>"
        f"</div>"
    )
    return send_email(subject, html)
