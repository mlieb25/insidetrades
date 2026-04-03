#!/usr/bin/env python3
"""Cron runner: Poll EDGAR, fetch market data, score, trade, notify.

Called hourly during market hours by the scheduled task.
Uses native Gmail API via service account for email delivery.
Uses Perplexity Finance tools (via external-tool CLI) for market data.
"""
import json
import sys
import os
import subprocess
import traceback
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trade_monitor.main import run_poll_cycle
from trade_monitor.market_data import save_market_data
from trade_monitor.gmail_sender import send_signal_alert
from trade_monitor import config, state as store
from trade_monitor.logger import log_system, log_error


def call_finance_tool(tool_name: str, arguments: dict) -> dict:
    """Call a Perplexity finance tool via external-tool CLI."""
    payload = json.dumps({
        "source_id": "finance",
        "tool_name": tool_name,
        "arguments": arguments,
    })
    try:
        result = subprocess.run(
            ["external-tool", "call", payload],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return {"error": result.stderr}
        return json.loads(result.stdout)
    except Exception as e:
        return {"error": str(e)}


def fetch_market_data_for_tickers(tickers: list):
    """Fetch current quotes for a list of tickers and cache them."""
    if not tickers:
        return

    result = call_finance_tool("finance_quotes", {
        "ticker_symbols": tickers,
        "fields": ["price", "changesPercentage", "marketCap", "pe",
                    "volume", "avgVolume", "dayLow", "dayHigh",
                    "yearLow", "yearHigh", "previousClose"],
    })

    if "error" not in result:
        content = result.get("content", "")
        if isinstance(content, str):
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    for ticker, values in data.items():
                        save_market_data(ticker, values)
                elif isinstance(data, list):
                    for item in data:
                        t = item.get("symbol", item.get("ticker", ""))
                        if t:
                            save_market_data(t, item)
            except json.JSONDecodeError:
                pass


def main():
    now = datetime.now(timezone.utc)
    log_system(f"Cron poll starting at {now.isoformat()}")
    print(f"[{now.isoformat()}] Starting poll cycle...")

    # Step 1: Run the main poll cycle
    try:
        result = run_poll_cycle()
        print(json.dumps(result, indent=2, default=str))
    except Exception as e:
        log_error(f"Poll cycle error: {e}", {"traceback": traceback.format_exc()})
        print(f"Poll cycle error: {e}", file=sys.stderr)
        result = {"alerts": [], "errors": [str(e)]}

    # Step 2: Fetch market data for open positions
    try:
        portfolio_data = store.load_portfolio()
        open_tickers = list(set(
            p.get("ticker", "") for p in portfolio_data.get("positions", [])
            if p.get("ticker")
        ))
        if open_tickers:
            print(f"Fetching market data for: {open_tickers}")
            fetch_market_data_for_tickers(open_tickers)
    except Exception as e:
        log_error(f"Market data error: {e}")

    # Step 3: Send email alerts for new signals via Gmail API
    alerts = result.get("alerts", [])
    for alert in alerts:
        try:
            success = send_signal_alert(alert)
            status = "sent" if success else "failed"
            print(f"Email alert {status}: {alert.get('subject', 'N/A')}")
        except Exception as e:
            log_error(f"Email error: {e}")

    # Step 4: Summary
    print(f"\n[{datetime.now(timezone.utc).isoformat()}] Cycle complete.")
    print(f"  New filings:  {result.get('new_filings', 0)}")
    print(f"  Qualifying:   {result.get('qualifying_trades', 0)}")
    print(f"  Signals:      {result.get('signals_generated', 0)}")
    print(f"  Trades:       {result.get('trades_opened', 0)}")
    print(f"  Closed:       {result.get('positions_closed', 0)}")
    print(f"  Errors:       {len(result.get('errors', []))}")


if __name__ == "__main__":
    main()
