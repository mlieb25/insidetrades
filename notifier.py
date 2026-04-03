"""Notification formatting and logging.

Formats alerts for signals, daily digests, and weekly summaries.
Actual delivery (email, push) is handled by the cron runner.
"""
import json
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from . import config
from .models import TradeSignal, Position
from . import state as store


def format_signal_alert(signal: TradeSignal) -> Dict[str, str]:
    """Format a trade signal into notification content.

    Returns dict with 'subject', 'body_text', 'body_html'.
    """
    trade = signal.trade

    subject = (f"🔔 {signal.confidence} Signal: {signal.direction} {signal.ticker} "
               f"({signal.company}) — Score {signal.score:.0f}/100")

    body_lines = [
        f"═══════════════════════════════════════════",
        f"  INSIDER TRADE SIGNAL — {signal.confidence} CONVICTION",
        f"═══════════════════════════════════════════",
        f"",
        f"Ticker:     {signal.ticker} ({signal.company})",
        f"Direction:  {signal.direction}",
        f"Score:      {signal.score:.0f}/100 ({signal.confidence})",
        f"",
        f"── Insider Details ──────────────────────",
        f"Name:       {trade.owner_name}",
        f"Role:       {trade.insider_role}",
        f"Action:     {'Purchase' if trade.is_open_market_purchase else 'Sale'} "
        f"({trade.transaction_code})",
        f"Shares:     {trade.shares:,.0f}",
        f"Price:      ${trade.price_per_share:.2f}",
        f"Value:      ${trade.dollar_value:,.0f}",
        f"",
        f"── Trade Plan ──────────────────────────",
        f"Entry Zone: ${signal.entry_zone_low:.2f} – ${signal.entry_zone_high:.2f}",
        f"Stop Loss:  ${signal.stop_loss:.2f}",
        f"Target:     ${signal.take_profit:.2f}",
        f"Trail Stop: {signal.trailing_stop_pct:.1f}%",
        f"Position:   {signal.position_size_pct:.1f}% of capital",
        f"Max Hold:   {signal.max_holding_days} trading days",
        f"",
        f"── Timestamps ──────────────────────────",
        f"Trade Date:   {signal.original_trade_date}",
        f"Filing Found: {signal.filing_detected_at}",
        f"Alert Time:   {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"",
        f"── Reasons ─────────────────────────────",
    ]
    for r in signal.reasons:
        body_lines.append(f"  • {r}")

    body_lines.extend([
        f"",
        f"── Score Breakdown ─────────────────────",
    ])
    for factor, pts in signal.score_breakdown.items():
        body_lines.append(f"  {factor:25s} {pts:5.1f}")

    body_lines.extend([
        f"",
        f"Filing: {signal.filing_url}",
        f"",
        f"[PAPER TRADING MODE — No real orders placed]",
        f"",
    ])

    body_text = "\n".join(body_lines)

    # Simple HTML version
    body_html = f"<pre style='font-family: monospace;'>{body_text}</pre>"

    return {
        "subject": subject,
        "body_text": body_text,
        "body_html": body_html,
    }


def format_daily_digest(portfolio_summary: dict,
                        signals_today: List[dict],
                        closed_today: List[dict],
                        system_state: dict) -> Dict[str, str]:
    """Format a daily digest notification."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    subject = f"📊 Daily Digest — {today} — PnL: ${portfolio_summary.get('total_pnl', 0):+,.0f}"

    lines = [
        f"═══════════════════════════════════════════",
        f"  TRADE MONITOR DAILY DIGEST — {today}",
        f"═══════════════════════════════════════════",
        f"",
        f"── Portfolio ───────────────────────────",
        f"Total Value:   ${portfolio_summary.get('total_value', 0):,.2f}",
        f"Cash:          ${portfolio_summary.get('cash', 0):,.2f}",
        f"Open PnL:      ${portfolio_summary.get('open_pnl', 0):+,.2f}",
        f"Closed PnL:    ${portfolio_summary.get('closed_pnl', 0):+,.2f}",
        f"Total PnL:     ${portfolio_summary.get('total_pnl', 0):+,.2f} "
        f"({portfolio_summary.get('total_pnl_pct', 0):+.2f}%)",
        f"Open Positions: {portfolio_summary.get('open_positions', 0)}",
        f"",
        f"── Signals Today ({len(signals_today)}) ──────────────",
    ]

    if signals_today:
        for s in signals_today:
            lines.append(f"  {s.get('ticker', '?'):8s} {s.get('direction', '?'):6s} "
                         f"Score={s.get('score', 0):.0f} {s.get('classification', '?')}")
    else:
        lines.append("  No new signals today.")

    lines.append(f"")
    lines.append(f"── Positions Closed Today ({len(closed_today)}) ─────")

    if closed_today:
        for p in closed_today:
            lines.append(f"  {p.get('ticker', '?'):8s} {p.get('exit_rule', '?'):15s} "
                         f"PnL=${p.get('realized_pnl', 0):+,.2f}")
    else:
        lines.append("  No positions closed today.")

    lines.extend([
        f"",
        f"── System Health ───────────────────────",
        f"Filings Detected: {system_state.get('total_filings_detected', 0)}",
        f"Total Signals:    {system_state.get('total_signals_generated', 0)}",
        f"Errors Today:     {system_state.get('errors_today', 0)}",
        f"Last Poll:        {system_state.get('last_poll_time', 'N/A')}",
        f"",
        f"Sources: " + ", ".join(
            f"{k}={v}" for k, v in system_state.get('source_status', {}).items()
        ),
        f"",
    ])

    return {
        "subject": subject,
        "body_text": "\n".join(lines),
        "body_html": f"<pre style='font-family: monospace;'>{'<br>'.join(lines)}</pre>",
    }


def format_weekly_summary(portfolio_summary: dict,
                          performance: dict,
                          week_signals: List[dict],
                          week_number: int) -> Dict[str, str]:
    """Format a weekly performance summary."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    subject = (f"📈 Week {week_number} Summary — "
               f"PnL: ${portfolio_summary.get('total_pnl', 0):+,.0f} "
               f"({portfolio_summary.get('total_pnl_pct', 0):+.1f}%)")

    lines = [
        f"═══════════════════════════════════════════",
        f"  WEEKLY SUMMARY — Week {week_number} — {today}",
        f"═══════════════════════════════════════════",
        f"",
        f"── Portfolio ───────────────────────────",
        f"Total Value: ${portfolio_summary.get('total_value', 0):,.2f}",
        f"Total PnL:   ${portfolio_summary.get('total_pnl', 0):+,.2f} "
        f"({portfolio_summary.get('total_pnl_pct', 0):+.1f}%)",
        f"",
        f"── Performance ─────────────────────────",
        f"Trades Closed: {performance.get('total_trades', 0)}",
        f"Win Rate:      {performance.get('win_rate', 0):.1f}%",
        f"Avg Win:       ${performance.get('avg_win', 0):+,.2f}",
        f"Avg Loss:      ${performance.get('avg_loss', 0):+,.2f}",
        f"Profit Factor: {performance.get('profit_factor', 0):.2f}",
        f"Best Trade:    ${performance.get('best_trade', 0):+,.2f}",
        f"Worst Trade:   ${performance.get('worst_trade', 0):+,.2f}",
        f"",
        f"── Signals This Week ({len(week_signals)}) ────────────",
    ]

    for s in week_signals[:20]:
        lines.append(f"  {s.get('ticker', '?'):8s} {s.get('direction', '?'):6s} "
                     f"Score={s.get('score', 0):.0f} → {s.get('classification', '?')}")

    if performance.get("by_exit_rule"):
        lines.append(f"")
        lines.append(f"── Exit Rules ──────────────────────────")
        for rule, data in performance["by_exit_rule"].items():
            lines.append(f"  {rule:20s} {data['count']} trades  "
                         f"PnL=${data['total_pnl']:+,.2f}")

    lines.append(f"")
    return {
        "subject": subject,
        "body_text": "\n".join(lines),
        "body_html": f"<pre style='font-family: monospace;'>{'<br>'.join(lines)}</pre>",
    }


def log_notification(notification: Dict[str, str], channel: str = "email") -> None:
    """Log a notification to the notifications file."""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "channel": channel,
        "subject": notification.get("subject", ""),
        "sent": False,
    }
    store.append_record("notifications.json", record)
