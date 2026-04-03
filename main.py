"""Main orchestrator for the trade monitoring system.

Each function runs one logical cycle and is designed to be called by
cron jobs at different frequencies.
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from . import config
from .models import TradeSignal
from .edgar_poller import poll_new_filings
from .scorer import score_trade
from .portfolio import PaperPortfolio
from .notifier import (
    format_signal_alert, format_daily_digest,
    format_weekly_summary, log_notification,
)
from .market_data import get_market_context
from .logger import log_system, log_error, journal_entry
from . import state as store


def run_poll_cycle() -> Dict[str, Any]:
    """Run one complete poll → parse → score → trade → exit cycle.

    Returns a summary dict of actions taken.
    """
    now = datetime.now(timezone.utc)
    log_system("Poll cycle starting")

    # Load state
    sys_state = store.load_state()
    seen = store.load_seen_accessions()

    summary = {
        "timestamp": now.isoformat(),
        "new_filings": 0,
        "qualifying_trades": 0,
        "signals_generated": 0,
        "trades_opened": 0,
        "positions_closed": 0,
        "alerts": [],
        "errors": [],
    }

    # ── 1. Poll for new filings ───────────────────────────────────
    try:
        new_trades, seen = poll_new_filings(seen)
        store.save_seen_accessions(seen)
        summary["new_filings"] = len(new_trades)
    except Exception as e:
        log_error(f"Polling error: {e}")
        summary["errors"].append(f"Polling: {str(e)}")
        new_trades = []

    # ── 2. Filter qualifying trades ───────────────────────────────
    qualifying = []
    for trade in new_trades:
        # Store all detected filings
        store.append_record("filings.json", trade.to_dict())
        sys_state.total_filings_detected += 1

        # Only open-market purchases and sales
        if trade.transaction_code not in config.QUALIFYING_TX_CODES:
            continue
        if trade.dollar_value < config.MIN_DOLLAR_VALUE:
            continue
        qualifying.append(trade)

    summary["qualifying_trades"] = len(qualifying)

    # ── 3. Score each trade ───────────────────────────────────────
    signals: List[TradeSignal] = []
    for trade in qualifying:
        try:
            ctx = get_market_context(trade.ticker)
            signal = score_trade(trade, ctx)
            store.append_record("signals.json", signal.to_dict())
            sys_state.total_signals_generated += 1
            signals.append(signal)
        except Exception as e:
            log_error(f"Scoring error for {trade.ticker}: {e}")
            summary["errors"].append(f"Scoring {trade.ticker}: {str(e)}")

    summary["signals_generated"] = len(signals)

    # ── 4. Execute paper trades for approved signals ──────────────
    portfolio = PaperPortfolio()
    approved = [s for s in signals if s.classification == "REPLICATE"]

    for signal in approved:
        try:
            position = portfolio.open_position(signal)
            if position:
                summary["trades_opened"] += 1
                sys_state.total_trades_executed += 1

                # Generate alert
                alert = format_signal_alert(signal)
                log_notification(alert)
                summary["alerts"].append(alert)
        except Exception as e:
            log_error(f"Trade execution error for {signal.ticker}: {e}")
            summary["errors"].append(f"Trade {signal.ticker}: {str(e)}")

    # ── 5. Check exits on all open positions ──────────────────────
    try:
        closed = portfolio.check_all_exits()
        summary["positions_closed"] = len(closed)
        sys_state.total_trades_closed += len(closed)
    except Exception as e:
        log_error(f"Exit check error: {e}")
        summary["errors"].append(f"Exit checks: {str(e)}")

    # ── 6. Update system state ────────────────────────────────────
    sys_state.last_poll_time = now.isoformat()
    sys_state.last_heartbeat = now.isoformat()
    sys_state.capital_remaining = portfolio.cash
    days_elapsed = (now - datetime.fromisoformat(
        sys_state.system_start if sys_state.system_start else now.isoformat()
    )).days
    sys_state.experiment_day = days_elapsed
    store.save_state(sys_state)

    # ── 7. Journal entry if anything notable ──────────────────────
    if summary["signals_generated"] > 0 or summary["positions_closed"] > 0:
        journal_entry(
            f"Cycle: {summary['new_filings']} filings, "
            f"{summary['signals_generated']} signals, "
            f"{summary['trades_opened']} trades",
            f"Qualifying: {summary['qualifying_trades']}\n"
            f"Approved: {summary['trades_opened']}\n"
            f"Closed: {summary['positions_closed']}\n"
            f"Errors: {len(summary['errors'])}"
        )

    log_system("Poll cycle complete", summary)
    return summary


def run_daily_digest() -> Dict[str, str]:
    """Generate the daily digest notification content."""
    portfolio = PaperPortfolio()
    sys_state = store.load_state()

    # Get today's signals
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    all_signals = store.load_records("signals.json")
    today_signals = [s for s in all_signals
                     if s.get("signal_generated_at", "").startswith(today)]

    # Get today's closed positions
    today_closed = [p.to_dict() for p in portfolio.closed_positions
                    if p.closed_at and p.closed_at.startswith(today)]

    digest = format_daily_digest(
        portfolio.get_summary(),
        today_signals,
        today_closed,
        sys_state.to_dict(),
    )

    log_notification(digest, "daily_digest")
    journal_entry("Daily Digest Generated", digest["body_text"])
    return digest


def run_weekly_summary() -> Dict[str, str]:
    """Generate the weekly summary notification content."""
    portfolio = PaperPortfolio()

    # Calculate week number since experiment start
    now = datetime.now(timezone.utc)
    try:
        start = datetime.strptime(config.EXPERIMENT_START, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        week_num = max(1, ((now - start).days // 7) + 1)
    except ValueError:
        week_num = 1

    # Get this week's signals
    week_start = (now - timedelta(days=7)).isoformat()
    all_signals = store.load_records("signals.json")
    week_signals = [s for s in all_signals
                    if s.get("signal_generated_at", "") >= week_start]

    summary = format_weekly_summary(
        portfolio.get_summary(),
        portfolio.get_performance_metrics(),
        week_signals,
        week_num,
    )

    log_notification(summary, "weekly_summary")
    journal_entry("Weekly Summary Generated", summary["body_text"])
    return summary


def run_health_check() -> Dict[str, Any]:
    """Check system health and report any issues."""
    sys_state = store.load_state()
    now = datetime.now(timezone.utc)
    issues = []

    # Check last poll time
    if sys_state.last_poll_time:
        last_poll = datetime.fromisoformat(sys_state.last_poll_time)
        hours_since = (now - last_poll).total_seconds() / 3600
        if hours_since > 2:
            issues.append(f"No poll in {hours_since:.1f} hours")

    # Check error rate
    if sys_state.errors_today > 10:
        issues.append(f"{sys_state.errors_today} errors today")

    # Check source status
    for source, status in sys_state.source_status.items():
        if status not in ("OK", "NOT_STARTED"):
            issues.append(f"{source} status: {status}")

    return {
        "healthy": len(issues) == 0,
        "issues": issues,
        "last_poll": sys_state.last_poll_time,
        "experiment_day": sys_state.experiment_day,
        "state": sys_state.to_dict(),
    }
