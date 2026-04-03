"""Data models for the trade monitoring system."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import json


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Raw Filing ────────────────────────────────────────────────────────
@dataclass
class Filing:
    accession_no: str
    cik: str
    issuer_name: str
    ticker: str
    owner_name: str
    owner_cik: str
    filing_url: str
    index_url: str
    filing_date: str           # YYYY-MM-DD
    detected_at: str = field(default_factory=_ts)
    source: str = "SEC_EDGAR"  # SEC_EDGAR | SEDI | POLITICIAN

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Filing":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ── Parsed Insider Trade ──────────────────────────────────────────────
@dataclass
class InsiderTrade:
    # Filing reference
    accession_no: str
    filing_url: str
    index_url: str
    source: str = "SEC_EDGAR"

    # Issuer
    issuer_cik: str = ""
    issuer_name: str = ""
    ticker: str = ""

    # Owner
    owner_name: str = ""
    owner_cik: str = ""
    is_director: bool = False
    is_officer: bool = False
    is_ten_pct_owner: bool = False
    is_other: bool = False
    role_text: str = ""

    # Transaction
    transaction_code: str = ""         # P, S, F, M, A, G, etc.
    transaction_date: str = ""         # YYYY-MM-DD
    filing_date: str = ""              # YYYY-MM-DD
    security_title: str = ""
    shares: float = 0.0
    price_per_share: float = 0.0
    acquired_or_disposed: str = ""     # A or D
    shares_after: float = 0.0
    ownership_type: str = "D"          # D=direct, I=indirect
    footnotes: List[str] = field(default_factory=list)

    # Timestamps
    detected_at: str = field(default_factory=_ts)
    filing_timestamp: str = ""         # Full ISO timestamp if available

    @property
    def dollar_value(self) -> float:
        return abs(self.shares * self.price_per_share)

    @property
    def insider_role(self) -> str:
        roles = []
        if self.is_director:
            roles.append("Director")
        if self.is_officer:
            roles.append("Officer")
        if self.is_ten_pct_owner:
            roles.append("10% Owner")
        if self.is_other and self.role_text:
            roles.append(self.role_text)
        return ", ".join(roles) if roles else "Unknown"

    @property
    def is_open_market_purchase(self) -> bool:
        return self.transaction_code == "P"

    @property
    def is_open_market_sale(self) -> bool:
        return self.transaction_code == "S"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["dollar_value"] = self.dollar_value
        d["insider_role"] = self.insider_role
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "InsiderTrade":
        d2 = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**d2)


# ── Trade Signal ──────────────────────────────────────────────────────
@dataclass
class TradeSignal:
    signal_id: str
    trade: InsiderTrade = field(default=None)  # type: ignore
    ticker: str = ""
    company: str = ""
    direction: str = "LONG"            # LONG or SHORT
    score: float = 0.0
    confidence: str = "LOW"            # HIGH, MEDIUM, LOW
    classification: str = "REJECT"     # REPLICATE, WATCHLIST, REJECT

    # Entry
    entry_zone_low: float = 0.0
    entry_zone_high: float = 0.0
    position_size_pct: float = 0.0
    position_shares: int = 0

    # Exit
    stop_loss: float = 0.0
    take_profit: float = 0.0
    trailing_stop_pct: float = 0.0
    max_holding_days: int = 30

    # Reasons
    reasons: List[str] = field(default_factory=list)
    score_breakdown: Dict[str, float] = field(default_factory=dict)

    # Timestamps
    original_trade_date: str = ""
    filing_detected_at: str = ""
    signal_generated_at: str = field(default_factory=_ts)
    alert_sent_at: str = ""

    # Status
    status: str = "pending"            # pending, active, closed, rejected
    rejected_reason: str = ""

    # Links
    filing_url: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.trade:
            d["trade"] = self.trade.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TradeSignal":
        trade_d = d.pop("trade", None)
        obj = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        if trade_d and isinstance(trade_d, dict):
            obj.trade = InsiderTrade.from_dict(trade_d)
        return obj


# ── Simulated Order ───────────────────────────────────────────────────
@dataclass
class SimulatedOrder:
    order_id: str
    signal_id: str
    ticker: str
    direction: str = "LONG"
    entry_price: float = 0.0
    shares: int = 0
    fill_time: str = field(default_factory=_ts)
    stop_price: float = 0.0
    target_price: float = 0.0
    trailing_stop_pct: float = 0.0
    max_exit_date: str = ""
    status: str = "open"               # open, closed

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SimulatedOrder":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ── Position ──────────────────────────────────────────────────────────
@dataclass
class Position:
    position_id: str
    order_id: str
    signal_id: str
    ticker: str
    direction: str = "LONG"
    entry_price: float = 0.0
    shares: int = 0
    current_price: float = 0.0
    high_water_mark: float = 0.0

    # PnL
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    realized_pnl: float = 0.0

    # Stops
    stop_price: float = 0.0
    target_price: float = 0.0
    trailing_stop_price: float = 0.0
    trailing_active: bool = False

    # Dates
    opened_at: str = field(default_factory=_ts)
    max_exit_date: str = ""
    closed_at: str = ""
    exit_rule: str = ""                # time_stop, price_stop, profit_target, trailing_stop, event_stop
    exit_price: float = 0.0

    # Status
    status: str = "open"               # open, closed

    def update_price(self, price: float) -> None:
        self.current_price = price
        if price > self.high_water_mark:
            self.high_water_mark = price
        if self.direction == "LONG":
            self.unrealized_pnl = (price - self.entry_price) * self.shares
        else:
            self.unrealized_pnl = (self.entry_price - price) * self.shares
        cost = self.entry_price * self.shares
        self.unrealized_pnl_pct = (self.unrealized_pnl / cost * 100) if cost else 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Position":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ── System State ──────────────────────────────────────────────────────
@dataclass
class SystemState:
    last_poll_time: str = ""
    last_accession_seen: str = ""
    total_filings_detected: int = 0
    total_signals_generated: int = 0
    total_trades_executed: int = 0
    total_trades_closed: int = 0
    capital_remaining: float = 100_000
    experiment_day: int = 0
    system_start: str = field(default_factory=_ts)
    last_heartbeat: str = field(default_factory=_ts)
    errors_today: int = 0
    source_status: Dict[str, str] = field(default_factory=lambda: {
        "SEC_EDGAR": "OK",
        "SEDI": "NOT_STARTED",
        "POLITICIAN": "NOT_STARTED"
    })

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SystemState":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
