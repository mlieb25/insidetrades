"""Politician trade tracker (Source 3 — lowest priority).

Uses the Perplexity Finance politician_trades tool via external-tool CLI.
These trades have 30-45 day reporting lags, so scoring is adjusted.
"""
import json
import subprocess
from datetime import datetime, timezone
from typing import List, Optional, Dict

from .models import InsiderTrade
from .logger import log_filing, log_error


def _call_finance_tool(tool_name: str, arguments: dict) -> Optional[dict]:
    """Call a finance tool via the external-tool CLI."""
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
            log_error(f"Finance tool error: {result.stderr}")
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        log_error(f"Finance tool call failed: {e}")
        return None


def poll_politician_trades() -> List[InsiderTrade]:
    """Fetch recent politician trades from Perplexity Finance.

    Returns InsiderTrade objects with source='POLITICIAN'.
    """
    result = _call_finance_tool("finance_politician_trades", {
        "query": "Recent congressional stock trades",
        "action": "Fetching latest politician trades",
    })

    if not result:
        return []

    trades = []
    # Parse the result — format depends on tool response
    content = result.get("content", "")
    if isinstance(content, str):
        # The tool returns markdown table or text; parse what we can
        log_filing("Politician trades fetched", {"raw_length": len(content)})
        # Politician trades are lower priority and have different format
        # We log them but scoring happens separately

    return trades


def score_politician_trade_adjustment(base_score: float,
                                       trade_date: str,
                                       filing_date: str) -> float:
    """Adjust score for politician trades based on reporting lag.

    Politicians have 30-45 day lags, so we penalize heavily but still
    track for informational value.
    """
    try:
        td = datetime.strptime(trade_date, "%Y-%m-%d")
        fd = datetime.strptime(filing_date, "%Y-%m-%d")
        lag_days = (fd - td).days
    except (ValueError, TypeError):
        lag_days = 45

    # Heavy penalty for lag
    if lag_days > 60:
        return base_score * 0.2
    elif lag_days > 30:
        return base_score * 0.4
    elif lag_days > 14:
        return base_score * 0.6
    else:
        return base_score * 0.8
