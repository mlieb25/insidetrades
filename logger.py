"""Structured logging for the trade monitoring system."""
import json
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from . import config


def _ensure_dirs():
    os.makedirs(config.LOG_DIR, exist_ok=True)
    os.makedirs(config.DATA_DIR, exist_ok=True)


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_data"):
            log_obj["data"] = record.extra_data
        return json.dumps(log_obj, default=str)


def _make_logger(name: str, filename: str, level=logging.INFO) -> logging.Logger:
    _ensure_dirs()
    logger = logging.getLogger(f"trade_monitor.{name}")
    logger.setLevel(level)
    if not logger.handlers:
        fh = RotatingFileHandler(
            os.path.join(config.LOG_DIR, filename),
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
        )
        fh.setFormatter(JSONFormatter())
        logger.addHandler(fh)
    return logger


# Dedicated loggers
system_log = _make_logger("system", "system.log")
filings_log = _make_logger("filings", "filings.log")
signals_log = _make_logger("signals", "signals.log")
trades_log = _make_logger("trades", "trades.log")
errors_log = _make_logger("errors", "errors.log", logging.ERROR)


def log_with_data(logger: logging.Logger, level: int, msg: str, data: dict = None):
    """Log a message with optional structured data."""
    record = logger.makeRecord(
        logger.name, level, "(file)", 0, msg, (), None
    )
    if data:
        record.extra_data = data
    logger.handle(record)


def log_filing(msg: str, data: dict = None):
    log_with_data(filings_log, logging.INFO, msg, data)


def log_signal(msg: str, data: dict = None):
    log_with_data(signals_log, logging.INFO, msg, data)


def log_trade(msg: str, data: dict = None):
    log_with_data(trades_log, logging.INFO, msg, data)


def log_error(msg: str, data: dict = None):
    log_with_data(errors_log, logging.ERROR, msg, data)


def log_system(msg: str, data: dict = None):
    log_with_data(system_log, logging.INFO, msg, data)


# ── Human-Readable Journal ────────────────────────────────────────────
def journal_entry(title: str, body: str) -> None:
    """Append a human-readable entry to the journal."""
    _ensure_dirs()
    path = os.path.join(config.LOG_DIR, "journal.md")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"\n## [{ts}] {title}\n\n{body}\n\n---\n"
    with open(path, "a") as f:
        f.write(entry)
