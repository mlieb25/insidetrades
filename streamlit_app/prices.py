"""
prices.py — Live stock price fetcher for Insider Trade Tracker
Uses yfinance for real-time / delayed quotes.
"""

from typing import Optional, Dict, List
import streamlit as st
import yfinance as yf


@st.cache_data(ttl=120, show_spinner=False)
def get_quote(ticker: str) -> Optional[dict]:
    """
    Fetch a live quote for a single ticker.
    Returns dict with price, name, change info — or None on failure.
    """
    try:
        tk = yf.Ticker(ticker.strip().upper())
        info = tk.info or {}

        price = (
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("previousClose")
        )
        if price is None:
            return None

        prev = info.get("previousClose") or price
        change = price - prev
        change_pct = (change / prev * 100) if prev else 0

        return {
            "ticker": ticker.strip().upper(),
            "price": float(price),
            "prev_close": float(prev),
            "change": float(change),
            "change_pct": float(change_pct),
            "name": info.get("shortName") or info.get("longName") or "",
            "currency": info.get("currency", "USD"),
            "market_cap": info.get("marketCap"),
            "sector": info.get("sector", ""),
        }
    except Exception:
        return None


@st.cache_data(ttl=120, show_spinner=False)
def get_bulk_prices(tickers: List[str]) -> Dict[str, float]:
    """
    Fetch current prices for a list of tickers.
    Returns { 'AAPL': 182.50, 'TSLA': 245.30, ... }
    Missing / failed tickers are silently omitted.
    """
    if not tickers:
        return {}

    prices = {}
    for t in tickers:
        t_clean = t.strip().upper()
        if not t_clean:
            continue
        try:
            tk = yf.Ticker(t_clean)
            info = tk.info or {}
            price = (
                info.get("currentPrice")
                or info.get("regularMarketPrice")
                or info.get("previousClose")
            )
            if price is not None:
                prices[t_clean] = float(price)
        except Exception:
            continue

    return prices


@st.cache_data(ttl=300, show_spinner=False)
def search_ticker(query: str) -> List[dict]:
    """
    Search for tickers matching a query string (company name or symbol).
    Returns a list of dicts: [{"symbol": ..., "name": ..., "exchange": ...}, ...]
    """
    if not query or len(query) < 1:
        return []
    try:
        results = yf.Search(query)
        quotes = results.quotes if hasattr(results, "quotes") else []
        out = []
        for q in quotes[:8]:
            out.append({
                "symbol": q.get("symbol", ""),
                "name": q.get("shortname") or q.get("longname") or "",
                "exchange": q.get("exchange", ""),
                "type": q.get("quoteType", ""),
            })
        return out
    except Exception:
        return []
