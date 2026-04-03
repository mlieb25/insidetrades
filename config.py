"""Configuration constants for the trade monitoring system."""
import os

# Load .env file if present (no external dependency)
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

# ── Identity ──────────────────────────────────────────────────────────
USER_AGENT = "Mitchell Liebrecht mitchellgliebrecht@gmail.com"
EMAIL = "mitchellgliebrecht@gmail.com"
GMAIL_SENDER = "insidertraderagent@gmail.com"
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
TIMEZONE = "America/Vancouver"

# ── Mode ──────────────────────────────────────────────────────────────
PAPER_MODE = True  # Never place live trades unless explicitly switched

# ── Capital / Position Sizing ─────────────────────────────────────────
STARTING_CAPITAL = 100_000
MAX_POSITION_PCT = 0.05      # 5 % of capital per trade
MAX_PORTFOLIO_PCT = 0.30     # 30 % total exposure
SLIPPAGE = {"large": 0.001, "mid": 0.0025, "small": 0.005}

# ── Scoring ───────────────────────────────────────────────────────────
SCORE_THRESHOLD_HIGH = 80
SCORE_THRESHOLD_MEDIUM = 65
SCORE_THRESHOLD_WATCHLIST = 50

# ── Polling ───────────────────────────────────────────────────────────
POLL_INTERVAL_SEC = 60
SEC_RATE_LIMIT_PER_SEC = 10
SEC_ATOM_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar?"
    "action=getcurrent&type=4&dateb=&owner=include"
    "&count=40&search_text=&start=0&output=atom"
)
SEC_EFTS_URL = "https://efts.sec.gov/LATEST/search-index"

# ── Filtering ─────────────────────────────────────────────────────────
MIN_MARKET_CAP = 500_000_000
MIN_DOLLAR_VALUE = 50_000
MAX_LAG_HOURS = 72
QUALIFYING_TX_CODES = {"P", "S"}          # Open-market purchase / sale
PRIORITY_TX_CODES = {"P"}                 # Strong-signal purchases

# ── Exit Defaults ─────────────────────────────────────────────────────
ATR_PERIOD = 14
DEFAULT_STOP_ATR_MULT = 2.0
DEFAULT_TARGET_ATR_MULT = 3.0
TRAILING_TRIGGER_ATR = 1.5
TRAILING_DISTANCE_ATR = 1.0
MAX_HOLDING_DAYS = {"high": 60, "medium": 30, "low": 10}

# ── Paths ─────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(BASE_DIR, "logs")

# ── Experiment Window ─────────────────────────────────────────────────
EXPERIMENT_START = "2026-04-02"
EXPERIMENT_END = "2026-07-02"   # 90 days
