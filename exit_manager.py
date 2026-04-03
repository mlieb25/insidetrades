"""Exit rule engine for position management.

Exit frameworks:
  1. TimeStop     — Close after max holding period
  2. PriceStop    — Close if price hits stop loss (ATR-based)
  3. ProfitTarget — Close if price hits profit target
  4. TrailingStop — After reaching trigger profit, trail by distance
  5. EventStop    — Close on earnings proximity, halt, or contradictory filing
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

from .models import Position
from . import config
from .logger import log_trade


def check_exit(position: Position, current_price: float,
               earnings_within_days: int = 999,
               contradictory_filing: bool = False,
               halted: bool = False) -> Tuple[bool, str, float]:
    """Check all exit rules for a position.

    Args:
        position: The open position to check.
        current_price: Current market price.
        earnings_within_days: Days until next earnings report.
        contradictory_filing: Whether a contradictory insider filing exists.
        halted: Whether the stock is halted.

    Returns:
        (should_exit, exit_rule, exit_price)
    """
    position.update_price(current_price)

    # ── 1. Event Stop (highest priority) ──────────────────────────
    if halted:
        log_trade(f"EVENT STOP (halt): {position.ticker}", {"position_id": position.position_id})
        return True, "event_stop_halt", current_price

    if contradictory_filing:
        log_trade(f"EVENT STOP (contradictory filing): {position.ticker}",
                  {"position_id": position.position_id})
        return True, "event_stop_filing", current_price

    if earnings_within_days <= 2:
        log_trade(f"EVENT STOP (earnings proximity): {position.ticker}",
                  {"position_id": position.position_id, "days_to_earnings": earnings_within_days})
        return True, "event_stop_earnings", current_price

    # ── 2. Price Stop ─────────────────────────────────────────────
    if position.direction == "LONG" and current_price <= position.stop_price:
        log_trade(f"PRICE STOP: {position.ticker} hit stop at {current_price:.2f}",
                  {"position_id": position.position_id, "stop": position.stop_price})
        return True, "price_stop", position.stop_price  # Fill at stop

    if position.direction == "SHORT" and current_price >= position.stop_price:
        log_trade(f"PRICE STOP: {position.ticker} hit stop at {current_price:.2f}",
                  {"position_id": position.position_id, "stop": position.stop_price})
        return True, "price_stop", position.stop_price

    # ── 3. Profit Target ──────────────────────────────────────────
    if position.direction == "LONG" and current_price >= position.target_price:
        log_trade(f"PROFIT TARGET: {position.ticker} hit target at {current_price:.2f}",
                  {"position_id": position.position_id, "target": position.target_price})
        return True, "profit_target", position.target_price

    if position.direction == "SHORT" and current_price <= position.target_price:
        log_trade(f"PROFIT TARGET: {position.ticker} hit target at {current_price:.2f}",
                  {"position_id": position.position_id, "target": position.target_price})
        return True, "profit_target", position.target_price

    # ── 4. Trailing Stop ──────────────────────────────────────────
    trail_exit, trail_price = _check_trailing(position, current_price)
    if trail_exit:
        log_trade(f"TRAILING STOP: {position.ticker} at {trail_price:.2f}",
                  {"position_id": position.position_id})
        return True, "trailing_stop", trail_price

    # ── 5. Time Stop ─────────────────────────────────────────────
    if position.max_exit_date:
        try:
            max_date = datetime.fromisoformat(position.max_exit_date)
            if datetime.now(timezone.utc) >= max_date:
                log_trade(f"TIME STOP: {position.ticker} max hold reached",
                          {"position_id": position.position_id})
                return True, "time_stop", current_price
        except ValueError:
            pass

    return False, "", 0.0


def _check_trailing(position: Position, current_price: float) -> Tuple[bool, float]:
    """Check and update trailing stop logic."""
    if position.direction == "LONG":
        # Activate trailing after reaching trigger profit
        profit_pct = ((current_price - position.entry_price) / position.entry_price) * 100
        trigger_pct = config.TRAILING_TRIGGER_ATR * 2  # Rough estimate: 3%

        if profit_pct >= trigger_pct or position.trailing_active:
            position.trailing_active = True
            # Update trailing stop based on high water mark
            trail_distance = position.high_water_mark * (position.trailing_stop_price / position.entry_price
                                                          if position.trailing_stop_price > 0
                                                          else 0.02)
            new_trail = position.high_water_mark * (1 - position.trailing_stop_price / position.entry_price
                                                     if position.trailing_stop_price > 0
                                                     else (1 - 0.03))
            # Simpler approach: trail by trailing_stop_pct from high water mark
            if hasattr(position, 'trailing_stop_pct') and position.trailing_stop_pct > 0:
                new_trail = position.high_water_mark * (1 - position.trailing_stop_pct / 100)
            else:
                new_trail = position.high_water_mark * 0.97  # 3% default trail

            # Only ratchet up, never down
            if new_trail > position.trailing_stop_price:
                position.trailing_stop_price = round(new_trail, 2)

            if current_price <= position.trailing_stop_price:
                return True, position.trailing_stop_price

    return False, 0.0


def compute_exit_params(entry_price: float, direction: str,
                        atr_estimate: float = 0) -> dict:
    """Compute stop/target/trailing parameters for a new position."""
    if atr_estimate <= 0:
        atr_estimate = entry_price * 0.02  # 2% fallback

    if direction == "LONG":
        stop = round(entry_price - atr_estimate * config.DEFAULT_STOP_ATR_MULT, 2)
        target = round(entry_price + atr_estimate * config.DEFAULT_TARGET_ATR_MULT, 2)
    else:
        stop = round(entry_price + atr_estimate * config.DEFAULT_STOP_ATR_MULT, 2)
        target = round(entry_price - atr_estimate * config.DEFAULT_TARGET_ATR_MULT, 2)

    trailing_pct = round((atr_estimate * config.TRAILING_DISTANCE_ATR / entry_price) * 100, 2)

    return {
        "stop_price": stop,
        "target_price": target,
        "trailing_stop_pct": trailing_pct,
    }
