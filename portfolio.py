"""Paper portfolio: position sizing, simulated orders, PnL tracking."""
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import uuid

from . import config
from .models import TradeSignal, SimulatedOrder, Position
from .exit_manager import check_exit
from .market_data import get_current_price, estimate_slippage, estimate_cap_category
from .logger import log_trade, log_system
from . import state as store


class PaperPortfolio:
    """Manages the paper trading portfolio."""

    def __init__(self):
        data = store.load_portfolio()
        self.cash: float = data.get("cash", config.STARTING_CAPITAL)
        self.positions: List[Position] = [
            Position.from_dict(p) for p in data.get("positions", [])
        ]
        self.closed_positions: List[Position] = [
            Position.from_dict(p) for p in data.get("closed_positions", [])
        ]
        self.orders: List[SimulatedOrder] = [
            SimulatedOrder.from_dict(o) for o in data.get("orders", [])
        ]

    def save(self):
        """Persist portfolio to disk."""
        store.save_portfolio({
            "cash": self.cash,
            "positions": [p.to_dict() for p in self.positions],
            "closed_positions": [p.to_dict() for p in self.closed_positions],
            "orders": [o.to_dict() for o in self.orders],
        })

    # ── Open Position ─────────────────────────────────────────────
    def open_position(self, signal: TradeSignal) -> Optional[Position]:
        """Execute a simulated trade from a signal."""
        if signal.classification != "REPLICATE":
            return None

        # Check portfolio exposure limit
        total_exposure = sum(p.entry_price * p.shares for p in self.positions)
        total_value = self.cash + total_exposure
        if total_exposure / total_value >= config.MAX_PORTFOLIO_PCT:
            log_trade(f"SKIP {signal.ticker}: portfolio exposure limit reached",
                      {"exposure_pct": total_exposure / total_value * 100})
            return None

        # Position sizing
        position_value = total_value * (signal.position_size_pct / 100)
        entry_price = (signal.entry_zone_low + signal.entry_zone_high) / 2

        if entry_price <= 0:
            return None

        # Apply slippage
        market_cap = 0
        try:
            from .market_data import get_market_data
            mdata = get_market_data(signal.ticker)
            if mdata:
                market_cap = mdata.get("marketCap", 0)
        except Exception:
            pass

        slip = estimate_slippage(market_cap)
        if signal.direction == "LONG":
            fill_price = round(entry_price * (1 + slip), 2)
        else:
            fill_price = round(entry_price * (1 - slip), 2)

        shares = int(position_value / fill_price)
        if shares <= 0:
            return None

        cost = fill_price * shares
        if cost > self.cash:
            shares = int(self.cash * 0.95 / fill_price)  # Use 95% of remaining cash
            if shares <= 0:
                return None
            cost = fill_price * shares

        # Create order
        now = datetime.now(timezone.utc)
        max_exit = now + timedelta(days=signal.max_holding_days)

        order = SimulatedOrder(
            order_id=f"ORD-{uuid.uuid4().hex[:8].upper()}",
            signal_id=signal.signal_id,
            ticker=signal.ticker,
            direction=signal.direction,
            entry_price=fill_price,
            shares=shares,
            stop_price=signal.stop_loss,
            target_price=signal.take_profit,
            trailing_stop_pct=signal.trailing_stop_pct,
            max_exit_date=max_exit.isoformat(),
        )
        self.orders.append(order)

        # Create position
        position = Position(
            position_id=f"POS-{uuid.uuid4().hex[:8].upper()}",
            order_id=order.order_id,
            signal_id=signal.signal_id,
            ticker=signal.ticker,
            direction=signal.direction,
            entry_price=fill_price,
            shares=shares,
            current_price=fill_price,
            high_water_mark=fill_price,
            stop_price=signal.stop_loss,
            target_price=signal.take_profit,
            trailing_stop_price=0,
            max_exit_date=max_exit.isoformat(),
        )
        self.positions.append(position)

        # Deduct cash
        self.cash -= cost

        log_trade(f"OPENED {signal.direction} {signal.ticker}: "
                  f"{shares} shares @ ${fill_price:.2f} = ${cost:,.0f}",
                  {"position_id": position.position_id,
                   "signal_id": signal.signal_id,
                   "stop": signal.stop_loss,
                   "target": signal.take_profit})

        self.save()
        return position

    # ── Close Position ────────────────────────────────────────────
    def close_position(self, position: Position, exit_price: float,
                       exit_rule: str) -> Position:
        """Close an open position."""
        now = datetime.now(timezone.utc).isoformat()

        # Apply slippage to exit
        market_cap = 0
        slip = config.SLIPPAGE["mid"]
        if position.direction == "LONG":
            actual_exit = round(exit_price * (1 - slip), 2)
            pnl = (actual_exit - position.entry_price) * position.shares
        else:
            actual_exit = round(exit_price * (1 + slip), 2)
            pnl = (position.entry_price - actual_exit) * position.shares

        position.exit_price = actual_exit
        position.exit_rule = exit_rule
        position.closed_at = now
        position.realized_pnl = round(pnl, 2)
        position.status = "closed"

        # Return cash
        self.cash += position.entry_price * position.shares + pnl

        # Move to closed
        self.positions = [p for p in self.positions if p.position_id != position.position_id]
        self.closed_positions.append(position)

        log_trade(f"CLOSED {position.ticker}: {exit_rule} @ ${actual_exit:.2f} "
                  f"PnL=${pnl:+,.2f}",
                  {"position_id": position.position_id, "exit_rule": exit_rule,
                   "pnl": pnl})

        self.save()
        return position

    # ── Check All Exits ───────────────────────────────────────────
    def check_all_exits(self) -> List[Position]:
        """Check exit conditions for all open positions."""
        closed = []
        for pos in list(self.positions):
            price = get_current_price(pos.ticker)
            if price is None:
                continue

            should_exit, rule, exit_price = check_exit(pos, price)
            if should_exit:
                closed_pos = self.close_position(pos, exit_price, rule)
                closed.append(closed_pos)

        return closed

    # ── Portfolio Metrics ─────────────────────────────────────────
    def get_summary(self) -> Dict[str, Any]:
        """Get current portfolio summary."""
        positions_value = sum(
            p.current_price * p.shares for p in self.positions
        )
        total_value = self.cash + positions_value
        total_pnl = total_value - config.STARTING_CAPITAL
        open_pnl = sum(p.unrealized_pnl for p in self.positions)
        closed_pnl = sum(p.realized_pnl for p in self.closed_positions)

        return {
            "cash": round(self.cash, 2),
            "positions_value": round(positions_value, 2),
            "total_value": round(total_value, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl / config.STARTING_CAPITAL * 100, 2),
            "open_positions": len(self.positions),
            "closed_positions": len(self.closed_positions),
            "open_pnl": round(open_pnl, 2),
            "closed_pnl": round(closed_pnl, 2),
        }

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Calculate detailed performance metrics."""
        if not self.closed_positions:
            return {"message": "No closed positions yet"}

        wins = [p for p in self.closed_positions if p.realized_pnl > 0]
        losses = [p for p in self.closed_positions if p.realized_pnl <= 0]

        win_rate = len(wins) / len(self.closed_positions) * 100 if self.closed_positions else 0
        avg_win = sum(p.realized_pnl for p in wins) / len(wins) if wins else 0
        avg_loss = sum(p.realized_pnl for p in losses) / len(losses) if losses else 0

        # Group by exit rule
        by_rule = {}
        for p in self.closed_positions:
            rule = p.exit_rule or "unknown"
            if rule not in by_rule:
                by_rule[rule] = {"count": 0, "total_pnl": 0}
            by_rule[rule]["count"] += 1
            by_rule[rule]["total_pnl"] += p.realized_pnl

        return {
            "total_trades": len(self.closed_positions),
            "win_rate": round(win_rate, 1),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(abs(avg_win / avg_loss), 2) if avg_loss else float('inf'),
            "best_trade": round(max(p.realized_pnl for p in self.closed_positions), 2),
            "worst_trade": round(min(p.realized_pnl for p in self.closed_positions), 2),
            "by_exit_rule": by_rule,
        }
