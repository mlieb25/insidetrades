"""Crash-safe state persistence with atomic writes."""
import json
import os
import tempfile
from typing import Any, Set
from . import config
from .models import SystemState


def _atomic_write(filepath: str, data: Any) -> None:
    """Write JSON data atomically: write to temp file, then rename."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=os.path.dirname(filepath), suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp, filepath)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _load_json(filepath: str, default: Any = None) -> Any:
    """Load JSON file, returning default if not found."""
    if not os.path.exists(filepath):
        return default
    with open(filepath, "r") as f:
        return json.load(f)


# ── System State ──────────────────────────────────────────────────────
def save_state(state: SystemState) -> None:
    _atomic_write(os.path.join(config.DATA_DIR, "state.json"), state.to_dict())


def load_state() -> SystemState:
    d = _load_json(os.path.join(config.DATA_DIR, "state.json"))
    if d:
        return SystemState.from_dict(d)
    return SystemState(capital_remaining=config.STARTING_CAPITAL)


# ── Seen Accessions ──────────────────────────────────────────────────
def save_seen_accessions(accessions: Set[str]) -> None:
    _atomic_write(
        os.path.join(config.DATA_DIR, "seen_accessions.json"),
        sorted(accessions),
    )


def load_seen_accessions() -> Set[str]:
    data = _load_json(os.path.join(config.DATA_DIR, "seen_accessions.json"), [])
    return set(data)


# ── Generic List Store ────────────────────────────────────────────────
def append_record(filename: str, record: dict) -> None:
    """Append a record to a JSON-lines style list file."""
    filepath = os.path.join(config.DATA_DIR, filename)
    records = _load_json(filepath, [])
    records.append(record)
    _atomic_write(filepath, records)


def load_records(filename: str) -> list:
    return _load_json(os.path.join(config.DATA_DIR, filename), [])


def save_records(filename: str, records: list) -> None:
    _atomic_write(os.path.join(config.DATA_DIR, filename), records)


# ── Portfolio ─────────────────────────────────────────────────────────
def save_portfolio(portfolio_data: dict) -> None:
    _atomic_write(os.path.join(config.DATA_DIR, "portfolio.json"), portfolio_data)


def load_portfolio() -> dict:
    return _load_json(os.path.join(config.DATA_DIR, "portfolio.json"), {
        "cash": config.STARTING_CAPITAL,
        "positions": [],
        "closed_positions": [],
        "orders": [],
    })
