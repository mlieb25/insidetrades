"""
sheets.py — Google Sheets client for Insider Trade Tracker
Supports two auth modes:
  1. Service account JSON file (path from GOOGLE_CREDENTIALS_PATH in .env)
  2. Streamlit Cloud secrets ([gcp_service_account] in .streamlit/secrets.toml)
"""

import os
import streamlit as st
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

SPREADSHEET_ID = "10_2yzOFxMic_lBAJLHwLEkg_1N8lqoQBEpNSUMRfef4"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


@st.cache_resource(show_spinner="Connecting to Google Sheets…")
def get_client() -> gspread.Client:
    """Authenticate and return a gspread client (cached for the session)."""

    # ── Option A: Streamlit Cloud secrets ──────────────────────────────────
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        return gspread.authorize(creds)
    except (KeyError, FileNotFoundError):
        pass

    # ── Option B: Local service account JSON file ───────────────────────────
    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
    if creds_path and os.path.exists(creds_path):
        creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
        return gspread.authorize(creds)

    raise RuntimeError(
        "🔑 No Google credentials found.\n\n"
        "Set GOOGLE_CREDENTIALS_PATH in your .env file to point at your "
        "service_account.json, or add [gcp_service_account] to .streamlit/secrets.toml.\n\n"
        "See streamlit_app/README_SETUP.md for detailed instructions."
    )


@st.cache_resource(show_spinner="Opening spreadsheet…")
def get_spreadsheet() -> gspread.Spreadsheet:
    return get_client().open_by_key(SPREADSHEET_ID)


# ── Low-level helpers (mirror server.js) ────────────────────────────────────

def get_sheet_data(sheet_name: str) -> list:
    """Return all data rows (excluding header) for a given sheet tab."""
    ws = get_spreadsheet().worksheet(sheet_name)
    rows = ws.get_all_values()
    return rows[1:] if len(rows) > 1 else []


def get_settings() -> dict:
    rows = get_sheet_data("Settings")
    return {r[0]: r[1] for r in rows if r and r[0]}


def append_row(sheet_name: str, values: list) -> None:
    ws = get_spreadsheet().worksheet(sheet_name)
    ws.append_row(values, value_input_option="USER_ENTERED")


def update_row(sheet_name: str, row_number: int, values: list) -> None:
    """Update a specific 1-indexed row (row 1 = header, row 2 = first data row)."""
    ws = get_spreadsheet().worksheet(sheet_name)
    col_end = _col_letter(len(values))
    ws.update(f"A{row_number}:{col_end}{row_number}", [values], value_input_option="USER_ENTERED")


def delete_row(sheet_name: str, row_index: int) -> None:
    """Delete a data row by its 0-based index in the data (not counting header)."""
    ws = get_spreadsheet().worksheet(sheet_name)
    # row_index 0 → sheet row 2 (1 for header + 1 for 1-indexing)
    ws.delete_rows(row_index + 2)


def _col_letter(n: int) -> str:
    """Convert column number (1-based) to spreadsheet letter (A, B, ... Z, AA...)."""
    result = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result
