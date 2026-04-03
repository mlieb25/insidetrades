"""Google Sheets integration for trade logging and live dashboard data.

Writes filings, signals, positions, portfolio snapshots, and system state
to a shared Google Sheet using a GCP service account.
The sheet serves as the live data layer for the public dashboard.
"""
import os
from datetime import datetime, timezone
from typing import List, Optional, Any

from . import config
from .logger import log_system, log_error

# Lazy-loaded service
_sheets_service = None

SPREADSHEET_ID = "10_2yzOFxMic_lBAJLHwLEkg_1N8lqoQBEpNSUMRfef4"

# ── Sheet Names & Headers ─────────────────────────────────────────────

SHEET_FILINGS = "Filings"
SHEET_SIGNALS = "Signals"
SHEET_OPEN_POSITIONS = "Open Positions"
SHEET_CLOSED_POSITIONS = "Closed Positions"
SHEET_PORTFOLIO = "Portfolio Snapshots"
SHEET_SYSTEM = "System Log"

HEADERS = {
    SHEET_FILINGS: [
        "Detected At", "Accession No", "Source", "Ticker", "Issuer",
        "Insider Name", "Insider Role", "Tx Code", "Tx Date",
        "Shares", "Price", "Dollar Value", "Acquired/Disposed",
        "Shares After", "Filing URL",
    ],
    SHEET_SIGNALS: [
        "Signal ID", "Generated At", "Ticker", "Company", "Direction",
        "Score", "Confidence", "Classification", "Status",
        "Insider Name", "Insider Role", "Tx Code", "Trade Date",
        "Shares", "Price", "Dollar Value",
        "Entry Low", "Entry High", "Stop Loss", "Take Profit",
        "Trailing %", "Position Size %", "Max Hold Days",
        "Reasons", "Score Breakdown", "Filing URL",
    ],
    SHEET_OPEN_POSITIONS: [
        "Position ID", "Signal ID", "Ticker", "Direction",
        "Entry Price", "Shares", "Cost Basis",
        "Current Price", "Unrealized PnL $", "Unrealized PnL %",
        "Stop Price", "Target Price", "Opened At", "Max Exit Date",
    ],
    SHEET_CLOSED_POSITIONS: [
        "Position ID", "Signal ID", "Ticker", "Direction",
        "Entry Price", "Exit Price", "Shares",
        "Realized PnL $", "Realized PnL %", "Exit Rule",
        "Opened At", "Closed At", "Days Held",
    ],
    SHEET_PORTFOLIO: [
        "Timestamp", "Cash", "Positions Value", "Total Value",
        "Total PnL $", "Total PnL %", "Open Positions", "Closed Positions",
        "Win Rate %", "Experiment Day",
    ],
    SHEET_SYSTEM: [
        "Timestamp", "Event", "Details",
        "Filings Detected", "Signals Generated", "Trades Executed",
        "Errors", "Source Status",
    ],
}


def _get_service():
    """Build and cache the Google Sheets API service."""
    global _sheets_service
    if _sheets_service is not None:
        return _sheets_service

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds_path = os.path.join(config.BASE_DIR, "credentials",
                                  "service_account.json")
        if not os.path.exists(creds_path):
            creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")

        if not creds_path or not os.path.exists(creds_path):
            log_error("Service account credentials not found for Sheets")
            return None

        SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
        credentials = service_account.Credentials.from_service_account_file(
            creds_path, scopes=SCOPES
        )
        _sheets_service = build("sheets", "v4", credentials=credentials)
        log_system("Google Sheets API service initialized")
        return _sheets_service

    except Exception as e:
        log_error(f"Failed to initialize Sheets API: {e}")
        return None


def _get_sheet(spreadsheet_id: str = SPREADSHEET_ID):
    """Get the spreadsheets resource."""
    service = _get_service()
    if not service:
        return None
    return service.spreadsheets()


# ── Sheet Setup ───────────────────────────────────────────────────────

def ensure_sheets_exist():
    """Create all required sheet tabs and write headers if they don't exist."""
    sheet = _get_sheet()
    if not sheet:
        return False

    try:
        # Get existing sheet names
        meta = sheet.get(spreadsheetId=SPREADSHEET_ID).execute()
        existing = {s["properties"]["title"] for s in meta.get("sheets", [])}

        requests = []
        for tab_name in HEADERS:
            if tab_name not in existing:
                requests.append({
                    "addSheet": {
                        "properties": {"title": tab_name}
                    }
                })

        # Create missing tabs
        if requests:
            sheet.batchUpdate(
                spreadsheetId=SPREADSHEET_ID,
                body={"requests": requests},
            ).execute()
            log_system(f"Created sheet tabs: {[r['addSheet']['properties']['title'] for r in requests]}")

        # Write headers to each tab (row 1)
        for tab_name, headers in HEADERS.items():
            _write_headers(sheet, tab_name, headers)

        # Delete default Sheet1 if it exists and isn't one of ours
        if "Sheet1" in existing and "Sheet1" not in HEADERS:
            meta2 = sheet.get(spreadsheetId=SPREADSHEET_ID).execute()
            for s in meta2.get("sheets", []):
                if s["properties"]["title"] == "Sheet1":
                    try:
                        sheet.batchUpdate(
                            spreadsheetId=SPREADSHEET_ID,
                            body={"requests": [{"deleteSheet": {"sheetId": s["properties"]["sheetId"]}}]},
                        ).execute()
                    except Exception:
                        pass  # May fail if it's the only sheet

        log_system("All sheet tabs verified with headers")
        return True

    except Exception as e:
        log_error(f"Failed to set up sheets: {e}")
        return False


def _write_headers(sheet, tab_name: str, headers: list):
    """Write header row to a sheet tab (only if row 1 is empty)."""
    try:
        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{tab_name}'!A1:Z1",
        ).execute()

        existing_headers = result.get("values", [[]])[0] if result.get("values") else []
        if existing_headers:
            return  # Headers already exist

        sheet.values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{tab_name}'!A1",
            valueInputOption="RAW",
            body={"values": [headers]},
        ).execute()

    except Exception as e:
        log_error(f"Failed to write headers for {tab_name}: {e}")


# ── Data Writing ──────────────────────────────────────────────────────

def _append_rows(tab_name: str, rows: List[List[Any]]):
    """Append rows to a sheet tab."""
    sheet = _get_sheet()
    if not sheet or not rows:
        return

    try:
        sheet.values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{tab_name}'!A:Z",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        ).execute()
    except Exception as e:
        log_error(f"Failed to append to {tab_name}: {e}", {"rows": len(rows)})


def _overwrite_tab(tab_name: str, rows: List[List[Any]]):
    """Clear a tab (except headers) and write new data."""
    sheet = _get_sheet()
    if not sheet:
        return

    try:
        # Clear everything below headers
        sheet.values().clear(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{tab_name}'!A2:Z10000",
            body={},
        ).execute()

        if rows:
            sheet.values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=f"'{tab_name}'!A2",
                valueInputOption="USER_ENTERED",
                body={"values": rows},
            ).execute()

    except Exception as e:
        log_error(f"Failed to overwrite {tab_name}: {e}")


# ── Public API: Log Trades ────────────────────────────────────────────

def log_filing(trade) -> None:
    """Log a parsed insider trade to the Filings sheet."""
    row = [
        trade.detected_at,
        trade.accession_no,
        trade.source,
        trade.ticker,
        trade.issuer_name,
        trade.owner_name,
        trade.insider_role,
        trade.transaction_code,
        trade.transaction_date,
        trade.shares,
        trade.price_per_share,
        trade.dollar_value,
        trade.acquired_or_disposed,
        trade.shares_after,
        trade.filing_url,
    ]
    _append_rows(SHEET_FILINGS, [row])


def log_signal(signal) -> None:
    """Log a scored trade signal to the Signals sheet."""
    trade = signal.trade
    reasons_str = " | ".join(signal.reasons) if signal.reasons else ""
    breakdown_str = ", ".join(f"{k}={v}" for k, v in signal.score_breakdown.items())

    row = [
        signal.signal_id,
        signal.signal_generated_at,
        signal.ticker,
        signal.company,
        signal.direction,
        signal.score,
        signal.confidence,
        signal.classification,
        signal.status,
        trade.owner_name if trade else "",
        trade.insider_role if trade else "",
        trade.transaction_code if trade else "",
        signal.original_trade_date,
        trade.shares if trade else 0,
        trade.price_per_share if trade else 0,
        trade.dollar_value if trade else 0,
        signal.entry_zone_low,
        signal.entry_zone_high,
        signal.stop_loss,
        signal.take_profit,
        signal.trailing_stop_pct,
        signal.position_size_pct,
        signal.max_holding_days,
        reasons_str,
        breakdown_str,
        signal.filing_url,
    ]
    _append_rows(SHEET_SIGNALS, [row])


def sync_open_positions(positions: list) -> None:
    """Overwrite the Open Positions tab with current state."""
    rows = []
    for p in positions:
        cost = p.entry_price * p.shares
        pnl_pct = (p.unrealized_pnl / cost * 100) if cost else 0
        rows.append([
            p.position_id,
            p.signal_id,
            p.ticker,
            p.direction,
            p.entry_price,
            p.shares,
            round(cost, 2),
            p.current_price,
            round(p.unrealized_pnl, 2),
            round(pnl_pct, 2),
            p.stop_price,
            p.target_price,
            p.opened_at,
            p.max_exit_date,
        ])
    _overwrite_tab(SHEET_OPEN_POSITIONS, rows)


def log_closed_position(p) -> None:
    """Append a closed position to the Closed Positions sheet."""
    cost = p.entry_price * p.shares
    pnl_pct = (p.realized_pnl / cost * 100) if cost else 0
    try:
        opened = datetime.fromisoformat(p.opened_at)
        closed = datetime.fromisoformat(p.closed_at)
        days_held = (closed - opened).days
    except (ValueError, TypeError):
        days_held = 0

    row = [
        p.position_id,
        p.signal_id,
        p.ticker,
        p.direction,
        p.entry_price,
        p.exit_price,
        p.shares,
        round(p.realized_pnl, 2),
        round(pnl_pct, 2),
        p.exit_rule,
        p.opened_at,
        p.closed_at,
        days_held,
    ]
    _append_rows(SHEET_CLOSED_POSITIONS, [row])


def log_portfolio_snapshot(summary: dict, experiment_day: int = 0) -> None:
    """Append a portfolio snapshot row."""
    row = [
        datetime.now(timezone.utc).isoformat(),
        summary.get("cash", 0),
        summary.get("positions_value", 0),
        summary.get("total_value", 0),
        summary.get("total_pnl", 0),
        summary.get("total_pnl_pct", 0),
        summary.get("open_positions", 0),
        summary.get("closed_positions", 0),
        summary.get("win_rate", 0),
        experiment_day,
    ]
    _append_rows(SHEET_PORTFOLIO, [row])


def log_system_event(event: str, details: str, state=None) -> None:
    """Append a system event to the System Log sheet."""
    row = [
        datetime.now(timezone.utc).isoformat(),
        event,
        details,
        state.total_filings_detected if state else 0,
        state.total_signals_generated if state else 0,
        state.total_trades_executed if state else 0,
        state.errors_today if state else 0,
        str(state.source_status) if state else "",
    ]
    _append_rows(SHEET_SYSTEM, [row])
