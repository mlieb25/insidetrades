"""Market data cache and retrieval.

In the cron-based architecture, actual finance API calls happen in the
cron runner and results are saved to cache files.  This module reads
from those cache files so the scoring engine stays decoupled.
"""
import json
import os
import time
from typing import Optional, Dict, Any
from . import config


CACHE_FILE = os.path.join(config.DATA_DIR, "market_cache.json")
CACHE_TTL_SEC = 300  # 5 minutes


def _load_cache() -> dict:
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_cache(cache: dict) -> None:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2, default=str)


def save_market_data(ticker: str, data: Dict[str, Any]) -> None:
    """Cache market data for a ticker."""
    cache = _load_cache()
    cache[ticker.upper()] = {
        "data": data,
        "updated_at": time.time(),
    }
    _save_cache(cache)


def get_market_data(ticker: str) -> Optional[Dict[str, Any]]:
    """Get cached market data for a ticker."""
    cache = _load_cache()
    entry = cache.get(ticker.upper())
    if not entry:
        return None
    # Check staleness
    age = time.time() - entry.get("updated_at", 0)
    if age > CACHE_TTL_SEC * 12:  # 1 hour hard expiry
        return None
    return entry.get("data")


def get_current_price(ticker: str) -> Optional[float]:
    """Get the last known price for a ticker."""
    data = get_market_data(ticker)
    if data:
        return data.get("price")
    return None


def get_market_context(ticker: str) -> Dict[str, Any]:
    """Get full market context for analysis."""
    data = get_market_data(ticker) or {}
    return {
        "price": data.get("price", 0),
        "change_pct": data.get("changesPercentage", 0),
        "market_cap": data.get("marketCap", 0),
        "pe": data.get("pe", 0),
        "volume": data.get("volume", 0),
        "avg_volume": data.get("avgVolume", 0),
        "day_low": data.get("dayLow", 0),
        "day_high": data.get("dayHigh", 0),
        "year_low": data.get("yearLow", 0),
        "year_high": data.get("yearHigh", 0),
        "prev_close": data.get("previousClose", 0),
    }


def estimate_cap_category(market_cap: float) -> str:
    """Classify market cap for slippage and liquidity filtering."""
    if market_cap >= 10_000_000_000:
        return "large"
    elif market_cap >= 2_000_000_000:
        return "mid"
    elif market_cap >= config.MIN_MARKET_CAP:
        return "small"
    else:
        return "micro"


def estimate_slippage(market_cap: float) -> float:
    """Get slippage assumption based on market cap."""
    cat = estimate_cap_category(market_cap)
    return config.SLIPPAGE.get(cat, config.SLIPPAGE["small"])
