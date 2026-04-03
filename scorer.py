"""Trade scoring engine: 0-100 composite score with factor breakdown."""
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
import uuid

from . import config
from .models import InsiderTrade, TradeSignal
from .market_data import get_market_context, estimate_cap_category
from .logger import log_signal
from . import state as store


def score_trade(trade: InsiderTrade, market_ctx: Optional[dict] = None) -> TradeSignal:
    """Score an insider trade and produce a TradeSignal.

    Factors (total 100):
      filing_freshness   0-15
      insider_seniority  0-20
      transaction_type   0-15
      dollar_size        0-15
      cluster_buying     0-10
      price_gap          0-10
      liquidity          0-5
      market_regime      0-10
    """
    if market_ctx is None:
        market_ctx = get_market_context(trade.ticker)

    breakdown: Dict[str, float] = {}
    reasons = []

    # ── 1. Filing Freshness (0-15) ────────────────────────────────
    freshness = _score_freshness(trade)
    breakdown["filing_freshness"] = freshness

    # ── 2. Insider Seniority (0-20) ───────────────────────────────
    seniority = _score_seniority(trade)
    breakdown["insider_seniority"] = seniority
    reasons.append(f"Insider: {trade.owner_name} ({trade.insider_role})")

    # ── 3. Transaction Type (0-15) ────────────────────────────────
    tx_score = _score_transaction_type(trade)
    breakdown["transaction_type"] = tx_score
    if tx_score == 0:
        # Non-qualifying transaction → reject
        return _make_signal(trade, 0, breakdown, reasons + ["Non-qualifying transaction type"],
                            "REJECT", f"Transaction code '{trade.transaction_code}' not P or S")

    # ── 4. Dollar Size (0-15) ─────────────────────────────────────
    size_score = _score_dollar_size(trade)
    breakdown["dollar_size"] = size_score
    reasons.append(f"Trade value: ${trade.dollar_value:,.0f} ({trade.shares:,.0f} shares @ ${trade.price_per_share:.2f})")

    if trade.dollar_value < config.MIN_DOLLAR_VALUE:
        return _make_signal(trade, sum(breakdown.values()), breakdown,
                            reasons + [f"Below minimum ${config.MIN_DOLLAR_VALUE:,} threshold"],
                            "REJECT", "Dollar value too small")

    # ── 5. Cluster Buying (0-10) ──────────────────────────────────
    cluster = _score_cluster(trade)
    breakdown["cluster_buying"] = cluster

    # ── 6. Price Gap (0-10) ───────────────────────────────────────
    gap_score, gap_pct = _score_price_gap(trade, market_ctx)
    breakdown["price_gap"] = gap_score
    if gap_pct is not None:
        reasons.append(f"Current price vs insider price: {gap_pct:+.1f}%")

    if gap_pct is not None and gap_pct > 15:
        return _make_signal(trade, sum(breakdown.values()), breakdown,
                            reasons + ["Price moved >15% above insider price"],
                            "REJECT", "Price gap too large")

    # ── 7. Liquidity (0-5) ────────────────────────────────────────
    liq_score = _score_liquidity(market_ctx)
    breakdown["liquidity"] = liq_score

    mkt_cap = market_ctx.get("market_cap", 0)
    if mkt_cap > 0 and mkt_cap < config.MIN_MARKET_CAP:
        return _make_signal(trade, sum(breakdown.values()), breakdown,
                            reasons + [f"Market cap ${mkt_cap/1e9:.1f}B below minimum"],
                            "REJECT", "Illiquid / micro-cap")

    # ── 8. Market Regime (0-10) ───────────────────────────────────
    regime_score = _score_regime(trade, market_ctx)
    breakdown["market_regime"] = regime_score

    # ── Total Score ───────────────────────────────────────────────
    total = sum(breakdown.values())

    # Check filing lag
    lag_hours = _filing_lag_hours(trade)
    if lag_hours and lag_hours > config.MAX_LAG_HOURS:
        return _make_signal(trade, total, breakdown,
                            reasons + [f"Filing lag {lag_hours:.0f}h exceeds {config.MAX_LAG_HOURS}h max"],
                            "REJECT", "Filing too stale")

    # ── Classify ──────────────────────────────────────────────────
    if total >= config.SCORE_THRESHOLD_HIGH:
        classification = "REPLICATE"
        confidence = "HIGH"
        hold_days = config.MAX_HOLDING_DAYS["high"]
        pos_pct = config.MAX_POSITION_PCT
        reasons.append(f"HIGH conviction signal (score {total:.0f}/100)")
    elif total >= config.SCORE_THRESHOLD_MEDIUM:
        classification = "REPLICATE"
        confidence = "MEDIUM"
        hold_days = config.MAX_HOLDING_DAYS["medium"]
        pos_pct = config.MAX_POSITION_PCT * 0.5
        reasons.append(f"MEDIUM conviction signal (score {total:.0f}/100)")
    elif total >= config.SCORE_THRESHOLD_WATCHLIST:
        classification = "WATCHLIST"
        confidence = "LOW"
        hold_days = config.MAX_HOLDING_DAYS["low"]
        pos_pct = 0
        reasons.append(f"Watchlist only (score {total:.0f}/100)")
    else:
        return _make_signal(trade, total, breakdown,
                            reasons + [f"Below threshold (score {total:.0f}/100)"],
                            "REJECT", f"Score {total:.0f} below {config.SCORE_THRESHOLD_WATCHLIST}")

    # ── Compute Entry / Stop / Target ─────────────────────────────
    current_price = market_ctx.get("price", trade.price_per_share)
    if current_price <= 0:
        current_price = trade.price_per_share

    # Entry zone: within 1% of current price
    entry_low = current_price * 0.995
    entry_high = current_price * 1.005

    # ATR estimate: use day range as proxy if no ATR data
    day_range = market_ctx.get("day_high", 0) - market_ctx.get("day_low", 0)
    atr_est = max(day_range, current_price * 0.02)  # At least 2% as floor

    direction = "LONG" if trade.is_open_market_purchase else "SHORT"

    if direction == "LONG":
        stop = current_price - (atr_est * config.DEFAULT_STOP_ATR_MULT)
        target = current_price + (atr_est * config.DEFAULT_TARGET_ATR_MULT)
    else:
        stop = current_price + (atr_est * config.DEFAULT_STOP_ATR_MULT)
        target = current_price - (atr_est * config.DEFAULT_TARGET_ATR_MULT)

    trailing_pct = (atr_est * config.TRAILING_DISTANCE_ATR / current_price) * 100

    signal = TradeSignal(
        signal_id=f"SIG-{uuid.uuid4().hex[:8].upper()}",
        trade=trade,
        ticker=trade.ticker,
        company=trade.issuer_name,
        direction=direction,
        score=round(total, 1),
        confidence=confidence,
        classification=classification,
        entry_zone_low=round(entry_low, 2),
        entry_zone_high=round(entry_high, 2),
        position_size_pct=round(pos_pct * 100, 1),
        stop_loss=round(stop, 2),
        take_profit=round(target, 2),
        trailing_stop_pct=round(trailing_pct, 2),
        max_holding_days=hold_days,
        reasons=reasons,
        score_breakdown=breakdown,
        original_trade_date=trade.transaction_date,
        filing_detected_at=trade.detected_at,
        filing_url=trade.filing_url,
        status="pending" if classification == "REPLICATE" else "watchlist",
    )

    log_signal(f"Signal generated: {signal.ticker} {signal.direction} "
               f"score={signal.score} class={signal.classification}",
               signal.to_dict())
    return signal


# ── Factor Scoring Functions ──────────────────────────────────────────

def _score_freshness(trade: InsiderTrade) -> float:
    """Score based on time since filing detection."""
    try:
        detected = datetime.fromisoformat(trade.detected_at)
        now = datetime.now(timezone.utc)
        hours = (now - detected).total_seconds() / 3600
    except (ValueError, TypeError):
        hours = 24  # default if can't parse

    if hours <= 2:
        return 15
    elif hours <= 6:
        return 12
    elif hours <= 12:
        return 8
    elif hours <= 24:
        return 4
    elif hours <= 48:
        return 2
    return 0


def _score_seniority(trade: InsiderTrade) -> float:
    """Score based on insider's role."""
    role_lower = trade.role_text.lower()

    # Check for C-suite titles
    if any(t in role_lower for t in ["ceo", "chief executive", "chairman", "chair"]):
        return 20
    if any(t in role_lower for t in ["cfo", "chief financial"]):
        return 17
    if any(t in role_lower for t in ["coo", "chief operating", "president"]):
        return 17
    if "chief" in role_lower or "c-suite" in role_lower:
        return 14

    if trade.is_officer:
        if any(t in role_lower for t in ["evp", "svp", "vp", "vice president"]):
            return 10
        return 12  # Generic officer

    if trade.is_director:
        return 12
    if trade.is_ten_pct_owner:
        return 8
    return 5


def _score_transaction_type(trade: InsiderTrade) -> float:
    """Score based on transaction code."""
    if trade.transaction_code == "P":
        return 15
    elif trade.transaction_code == "S":
        return 10
    return 0  # reject all others


def _score_dollar_size(trade: InsiderTrade) -> float:
    """Score based on total dollar value of transaction."""
    val = trade.dollar_value
    if val >= 5_000_000:
        return 15
    elif val >= 1_000_000:
        return 12
    elif val >= 500_000:
        return 10
    elif val >= 100_000:
        return 7
    elif val >= 50_000:
        return 5
    return 0


def _score_cluster(trade: InsiderTrade) -> float:
    """Score for cluster buying: multiple insiders buying same ticker recently.

    Reads from stored recent signals to detect clusters.
    """
    try:
        recent_signals = store.load_records("signals.json")
    except Exception:
        return 3  # Default single-insider score

    # Count distinct insiders who bought this ticker in last 7 days
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    same_ticker_buyers = set()
    for s in recent_signals:
        t = s.get("trade", {})
        if (t.get("ticker") == trade.ticker and
                t.get("transaction_code") == "P" and
                s.get("signal_generated_at", "") > cutoff):
            same_ticker_buyers.add(t.get("owner_cik", ""))

    count = len(same_ticker_buyers)
    if count >= 3:
        return 10
    elif count >= 2:
        return 7
    return 3


def _score_price_gap(trade: InsiderTrade, ctx: dict) -> tuple:
    """Score based on current price vs insider's reported price."""
    current = ctx.get("price", 0)
    insider_price = trade.price_per_share

    if not current or not insider_price:
        return 5, None

    gap_pct = ((current - insider_price) / insider_price) * 100

    if trade.is_open_market_purchase:
        # For buys, we want price near or below insider price
        abs_gap = abs(gap_pct)
        if abs_gap <= 2:
            return 10, gap_pct
        elif abs_gap <= 5:
            return 7, gap_pct
        elif abs_gap <= 10:
            return 4, gap_pct
        else:
            return 0, gap_pct
    else:
        # For sales (short signals), gap in opposite direction
        return 5, gap_pct


def _score_liquidity(ctx: dict) -> float:
    """Score based on market cap."""
    cap = ctx.get("market_cap", 0)
    if cap >= 10_000_000_000:
        return 5
    elif cap >= 2_000_000_000:
        return 4
    elif cap >= 500_000_000:
        return 3
    return 0


def _score_regime(trade: InsiderTrade, ctx: dict) -> float:
    """Score based on market regime (simple trend assessment)."""
    change_pct = ctx.get("change_pct", 0)
    price = ctx.get("price", 0)
    year_low = ctx.get("year_low", 0)
    year_high = ctx.get("year_high", 0)

    # Simple regime: where is price relative to 52-week range?
    if year_high and year_low and price:
        position = (price - year_low) / (year_high - year_low) if (year_high - year_low) > 0 else 0.5
    else:
        position = 0.5

    if trade.is_open_market_purchase:
        # Insider buying near lows = contrarian value signal
        if position < 0.3:
            return 10  # Near 52-week low — strong contrarian
        elif position < 0.5:
            return 7
        elif position < 0.7:
            return 5
        else:
            return 3  # Buying near highs — less informative
    else:
        # Sale at highs
        if position > 0.8:
            return 7
        return 3

    return 5


def _filing_lag_hours(trade: InsiderTrade) -> Optional[float]:
    """Calculate hours between transaction date and detection."""
    try:
        tx_date = datetime.strptime(trade.transaction_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        detected = datetime.fromisoformat(trade.detected_at)
        return (detected - tx_date).total_seconds() / 3600
    except (ValueError, TypeError):
        return None


def _make_signal(trade, score, breakdown, reasons, classification, rejected_reason=""):
    """Create a signal for rejected/watchlist trades."""
    return TradeSignal(
        signal_id=f"SIG-{uuid.uuid4().hex[:8].upper()}",
        trade=trade,
        ticker=trade.ticker,
        company=trade.issuer_name,
        direction="LONG" if trade.is_open_market_purchase else "SHORT",
        score=round(score, 1),
        confidence="LOW",
        classification=classification,
        reasons=reasons,
        score_breakdown=breakdown,
        original_trade_date=trade.transaction_date,
        filing_detected_at=trade.detected_at,
        filing_url=trade.filing_url,
        status="rejected" if classification == "REJECT" else "watchlist",
        rejected_reason=rejected_reason,
    )


# Need uuid at module level
import uuid
