"""
app.py — Insider Trade Tracker (Streamlit)
Run with: streamlit run app.py
"""

import sys, os
# Ensure the app's own directory is on the path (required on Streamlit Cloud)
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import date, timedelta
import uuid

import sheets as sh
import prices


# ══════════════════════════════════════════════════════════════════════════════
# Page config & global CSS
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Insider Trade Tracker",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
/* ── Global ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: #0f1117; color: #e2e8f0; }

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1400px; }

/* ── Custom classes ── */
.app-title { font-family: 'JetBrains Mono', monospace; font-size: 1.1rem; font-weight: 600; letter-spacing: 0.08em; color: #00d4aa; padding-top: 4px; }
.paper-badge { background: rgba(255,167,38,0.15); color: #ffa726; border: 1px solid rgba(255,167,38,0.3); border-radius: 6px; padding: 3px 10px; font-size: 0.72rem; font-weight: 600; letter-spacing: 0.06em; }
.day-counter { font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; color: #6b7185; padding-top: 6px; }

.kpi-card { background: linear-gradient(135deg, #13151f 0%, #1a1d2e 100%); border: 1px solid #2a2d3a; border-radius: 12px; padding: 18px 20px; text-align: center; }
.kpi-label { font-size: 0.72rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: #6b7185; display: block; margin-bottom: 6px; }
.kpi-value { font-family: 'JetBrains Mono', monospace; font-size: 1.55rem; font-weight: 600; color: #e2e8f0; display: block; }
.kpi-sub { font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; display: block; margin-top: 4px; }
.kpi-sub.pos { color: #00d4aa; } .kpi-sub.neg { color: #ff6b6b; } .kpi-sub.neu { color: #6b7185; }

.section-header { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: #9aa0b0; border-bottom: 1px solid #2a2d3a; padding-bottom: 8px; margin-bottom: 1rem; }

[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }

/* ════ DARK THEME OVERRIDES ════ */

/* Buttons — default/secondary */
.stButton > button {
    background: #1e2130 !important;
    color: #c8cdd8 !important;
    border: 1px solid #2e3347 !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    transition: background 0.15s, border-color 0.15s !important;
}
.stButton > button:hover {
    background: #252a3d !important;
    border-color: #00d4aa !important;
    color: #e2e8f0 !important;
}

/* Primary form submit button */
.stFormSubmitButton > button {
    background: linear-gradient(135deg, #00b894, #00d4aa) !important;
    color: #0f1117 !important;
    border: none !important;
    font-weight: 700 !important;
    letter-spacing: 0.05em !important;
    border-radius: 8px !important;
}
.stFormSubmitButton > button:hover {
    background: linear-gradient(135deg, #00c9a7, #00e5bb) !important;
    color: #0f1117 !important;
}

/* Text / number / textarea inputs */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stTextArea > div > div > textarea {
    background: #13151f !important;
    border: 1px solid #2a2d3a !important;
    color: #e2e8f0 !important;
    border-radius: 8px !important;
}
.stTextInput > div > div > input::placeholder,
.stNumberInput > div > div > input::placeholder,
.stTextArea > div > div > textarea::placeholder { color: #3d4460 !important; }
.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: #00d4aa !important;
    box-shadow: 0 0 0 2px rgba(0,212,170,0.12) !important;
}

/* Selectbox */
[data-baseweb="select"] > div:first-child {
    background: #13151f !important;
    border: 1px solid #2a2d3a !important;
    color: #e2e8f0 !important;
    border-radius: 8px !important;
}
[data-baseweb="select"] span { color: #e2e8f0 !important; }
[data-baseweb="select"] svg { fill: #6b7185 !important; }
[data-baseweb="popover"] [role="listbox"],
[data-baseweb="menu"] ul {
    background: #1a1d2e !important;
    border: 1px solid #2a2d3a !important;
    border-radius: 8px !important;
}
[data-baseweb="menu"] li { background: #1a1d2e !important; color: #e2e8f0 !important; }
[data-baseweb="menu"] li:hover { background: #252a3d !important; }

/* Date input */
.stDateInput > div > div > input {
    background: #13151f !important;
    border: 1px solid #2a2d3a !important;
    color: #e2e8f0 !important;
    border-radius: 8px !important;
}

/* Number input steppers */
.stNumberInput button {
    background: #1e2130 !important;
    color: #9aa0b0 !important;
    border: 1px solid #2a2d3a !important;
}

/* Form labels */
label, .stTextInput label, .stNumberInput label,
.stSelectbox label, .stTextArea label, .stDateInput label {
    color: #9aa0b0 !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
}

/* Expander — header row */
[data-testid="stExpander"] details summary {
    background: #13151f !important;
    border: 1px solid #2a2d3a !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
    font-weight: 600 !important;
    padding: 12px 16px !important;
    list-style: none !important;
}
[data-testid="stExpander"] details[open] summary {
    border-radius: 10px 10px 0 0 !important;
    border-bottom-color: transparent !important;
}
[data-testid="stExpander"] details summary:hover {
    background: #1a1d2e !important;
    border-color: #00d4aa !important;
}
[data-testid="stExpander"] details summary p,
[data-testid="stExpander"] details summary span {
    color: #e2e8f0 !important;
}
/* Expander body */
[data-testid="stExpander"] details > div[data-testid="stExpanderDetails"] {
    background: #0d0f18 !important;
    border: 1px solid #2a2d3a !important;
    border-top: none !important;
    border-radius: 0 0 10px 10px !important;
    padding: 1rem !important;
}
/* Expander caret */
[data-testid="stExpander"] details summary svg { stroke: #6b7185 !important; }

/* Form container */
[data-testid="stForm"] {
    background: #0d0f18 !important;
    border: 1px solid #2a2d3a !important;
    border-radius: 10px !important;
    padding: 1rem 1.2rem !important;
}

/* st.metric */
[data-testid="metric-container"] {
    background: #13151f !important;
    border: 1px solid #1e2130 !important;
    border-radius: 8px !important;
    padding: 10px 14px !important;
}
[data-testid="stMetricLabel"] p { color: #6b7185 !important; font-size: 0.75rem !important; }
[data-testid="stMetricValue"] { color: #e2e8f0 !important; font-family: 'JetBrains Mono', monospace !important; }

/* Alerts */
[data-testid="stAlert"] {
    background: #1a1d2e !important;
    border: 1px solid #2a2d3a !important;
    border-radius: 8px !important;
    color: #9aa0b0 !important;
}

hr { border-color: #2a2d3a !important; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Helpers

# ══════════════════════════════════════════════════════════════════════════════

def fmt_usd(val) -> str:
    if val is None:
        return "--"
    try:
        v = float(val)
        sign = "-" if v < 0 else ""
        return f"{sign}${abs(v):,.2f}"
    except (TypeError, ValueError):
        return "--"


def fmt_pct(val) -> str:
    if val is None:
        return "--"
    try:
        v = float(val)
        sign = "+" if v > 0 else ""
        return f"{sign}{v:.2f}%"
    except (TypeError, ValueError):
        return "--"


def safe_float(val, default=0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def safe_int(val, default=0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def generate_trade_id() -> str:
    return "T-" + uuid.uuid4().hex[:6].upper()


def today_str() -> str:
    return date.today().isoformat()


def timestamp_str() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ══════════════════════════════════════════════════════════════════════════════
# Data loading
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=30, show_spinner=False)
def load_data():
    settings = sh.get_settings()
    starting_capital = safe_float(settings.get("starting_capital", 100000), 100000)
    default_stop_pct = safe_float(settings.get("default_stop_pct", 5), 5)
    default_target_pct = safe_float(settings.get("default_target_pct", 10), 10)
    default_exp_days = safe_int(settings.get("default_expiration_days", 60), 60)
    max_position_pct = safe_float(settings.get("max_position_pct", 10), 10)
    exp_start = settings.get("experiment_start", today_str())
    exp_end = settings.get("experiment_end", "")

    open_rows = sh.get_sheet_data("Open Positions")
    closed_rows = sh.get_sheet_data("Closed Trades")
    history_rows = sh.get_sheet_data("Portfolio History")

    # Fetch live prices for all open position tickers
    open_tickers = list({r[1].strip().upper() for r in open_rows if len(r) > 1 and r[1].strip()})
    latest_prices = prices.get_bulk_prices(open_tickers) if open_tickers else {}

    positions = []
    for r in open_rows:
        while len(r) < 20:
            r.append("")
            
        ticker = r[1].strip().upper()
        direction = r[3]
        entry_price = safe_float(r[5])
        shares = safe_int(r[6])
        cost_basis = safe_float(r[7])
        
        # Use live price if available, else fall back to sheet value
        current_price = latest_prices.get(ticker, safe_float(r[8]))
        
        # Calculate unrealized PnL dynamically
        if direction == "LONG":
            unrealized_pnl = (current_price - entry_price) * shares
        else: # SHORT
            unrealized_pnl = (entry_price - current_price) * shares
            
        unrealized_pct = (unrealized_pnl / cost_basis * 100) if cost_basis > 0 else 0.0

        positions.append({
            "trade_id": r[0], "ticker": r[1], "company": r[2],
            "direction": direction, "entry_date": r[4],
            "entry_price": entry_price,
            "shares": shares,
            "cost_basis": cost_basis,
            "current_price": current_price,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pct": unrealized_pct,
            "stop_loss": safe_float(r[11]),
            "take_profit": safe_float(r[12]),
            "trailing_stop_pct": safe_float(r[13]),
            "expiration_date": r[14],
            "thesis": r[15], "source": r[16],
            "insider_name": r[17], "insider_role": r[18], "filing_url": r[19],
        })

    closed_trades = []
    for r in closed_rows:
        while len(r) < 20:
            r.append("")
        closed_trades.append({
            "trade_id": r[0], "ticker": r[1], "company": r[2],
            "direction": r[3], "entry_date": r[4],
            "entry_price": safe_float(r[5]),
            "exit_date": r[6], "exit_price": safe_float(r[7]),
            "shares": safe_int(r[8]),
            "realized_pnl": safe_float(r[9]),
            "realized_pct": safe_float(r[10]),
            "exit_reason": r[11],
            "days_held": safe_int(r[12]),
            "stop_loss": safe_float(r[13]),
            "take_profit": safe_float(r[14]),
            "thesis": r[15], "source": r[16],
            "insider_name": r[17], "insider_role": r[18], "filing_url": r[19],
        })

    history = []
    for r in history_rows:
        while len(r) < 9:
            r.append("")
        history.append({
            "date": r[0], "cash": safe_float(r[1]),
            "positions_value": safe_float(r[2]),
            "total_value": safe_float(r[3]),
            "total_pnl": safe_float(r[4]),
            "total_pnl_pct": safe_float(r[5]),
            "open_count": safe_int(r[6]),
            "closed_count": safe_int(r[7]),
            "win_rate": safe_float(r[8]),
        })

    # ── Compute portfolio state ──────────────────────────────────────────────
    total_unrealized_pnl = sum(p["unrealized_pnl"] for p in positions)
    positions_value = sum(p["cost_basis"] for p in positions)
    realized_pnl = sum(t["realized_pnl"] for t in closed_trades)
    cash = starting_capital - positions_value + realized_pnl
    total_value = cash + positions_value + total_unrealized_pnl
    total_pnl = total_value - starting_capital
    total_pnl_pct = (total_pnl / starting_capital * 100) if starting_capital else 0

    wins = [t for t in closed_trades if t["realized_pnl"] > 0]
    losses = [t for t in closed_trades if t["realized_pnl"] <= 0]
    win_rate = (len(wins) / len(closed_trades) * 100) if closed_trades else 0
    avg_win = (sum(t["realized_pnl"] for t in wins) / len(wins)) if wins else 0
    avg_loss = (sum(abs(t["realized_pnl"]) for t in losses) / len(losses)) if losses else 0
    total_win_amt = sum(t["realized_pnl"] for t in wins)
    total_loss_amt = sum(abs(t["realized_pnl"]) for t in losses)
    profit_factor = (total_win_amt / total_loss_amt) if total_loss_amt > 0 else (float("inf") if total_win_amt > 0 else 0)
    best = max(closed_trades, key=lambda t: t["realized_pnl"], default=None)
    worst = min(closed_trades, key=lambda t: t["realized_pnl"], default=None)
    avg_days = (sum(t["days_held"] for t in closed_trades) / len(closed_trades)) if closed_trades else 0

    return {
        "settings": settings,
        "starting_capital": starting_capital,
        "default_stop_pct": default_stop_pct,
        "default_target_pct": default_target_pct,
        "default_exp_days": default_exp_days,
        "max_position_pct": max_position_pct,
        "exp_start": exp_start,
        "exp_end": exp_end,
        "positions": positions,
        "closed_trades": closed_trades,
        "history": history,
        "cash": cash,
        "positions_value": positions_value,
        "total_value": total_value,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "best_trade": best,
        "worst_trade": worst,
        "avg_days": avg_days,
        "wins": len(wins),
        "losses": len(losses),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Connect — show a friendly error if creds are missing
# ══════════════════════════════════════════════════════════════════════════════

try:
    d = load_data()
except RuntimeError as e:
    st.error(str(e))
    st.stop()
except Exception as e:
    st.error(f"Failed to load data from Google Sheets: {e}")
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# TOP BANNER
# ══════════════════════════════════════════════════════════════════════════════

exp_start = d["exp_start"]
start_date = date.fromisoformat(exp_start) if exp_start else date.today()
day_num = min(max((date.today() - start_date).days + 1, 1), 90)

col_title, col_badge, col_day, col_refresh = st.columns([4, 1, 1.5, 1])
with col_title:
    st.markdown('<div class="app-title">🎯 INSIDER TRADE TRACKER</div>', unsafe_allow_html=True)
with col_badge:
    st.markdown('<div style="padding-top:4px"><span class="paper-badge">PAPER TRADING</span></div>', unsafe_allow_html=True)
with col_day:
    st.markdown(f'<div class="day-counter" style="padding-top:6px">Day {day_num}/90 · {exp_start} → {d["exp_end"]}</div>', unsafe_allow_html=True)
with col_refresh:
    if st.button("↺ Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# KPI CARDS
# ══════════════════════════════════════════════════════════════════════════════

k1, k2, k3, k4 = st.columns(4)

pnl_color = "#00d4aa" if d["total_pnl"] >= 0 else "#ff6b6b"
pnl_sign = "+" if d["total_pnl"] >= 0 else ""

with k1:
    st.markdown(f"""
    <div class="kpi-card">
        <span class="kpi-label">Total Value</span>
        <span class="kpi-value">{fmt_usd(d["total_value"])}</span>
        <span class="kpi-sub" style="color:{pnl_color}">{pnl_sign}{fmt_usd(d["total_pnl"])} ({fmt_pct(d["total_pnl_pct"])})</span>
    </div>""", unsafe_allow_html=True)

with k2:
    cash_pct = (d["cash"] / d["total_value"] * 100) if d["total_value"] else 100
    st.markdown(f"""
    <div class="kpi-card">
        <span class="kpi-label">Cash Available</span>
        <span class="kpi-value">{fmt_usd(d["cash"])}</span>
        <span class="kpi-sub neu">{cash_pct:.1f}% of portfolio</span>
    </div>""", unsafe_allow_html=True)

with k3:
    st.markdown(f"""
    <div class="kpi-card">
        <span class="kpi-label">Open Positions</span>
        <span class="kpi-value">{len(d["positions"])}</span>
        <span class="kpi-sub neu">{fmt_usd(d["positions_value"])} invested</span>
    </div>""", unsafe_allow_html=True)

with k4:
    wr_str = f"{d['win_rate']:.1f}%" if d["closed_trades"] else "--%"
    st.markdown(f"""
    <div class="kpi-card">
        <span class="kpi-label">Win Rate</span>
        <span class="kpi-value">{wr_str}</span>
        <span class="kpi-sub neu">{len(d["closed_trades"])} closed trades</span>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# MAIN LAYOUT: Left (forms + tables) | Right (charts + stats)
# ══════════════════════════════════════════════════════════════════════════════

left, right = st.columns([3, 2], gap="large")


# ─────────────────────────────────────────────────────────────────────────────
# LEFT — New Trade Form
# ─────────────────────────────────────────────────────────────────────────────

with left:
    with st.expander("⚡ Enter New Trade", expanded=True):
        st.markdown('<div class="section-header">Ticker</div>', unsafe_allow_html=True)

        # ── Ticker input (outside the form so it triggers a live lookup) ───
        nt_ticker_raw = st.text_input(
            "Ticker *",
            placeholder="AAPL",
            key="nt_ticker",
            label_visibility="collapsed",
        ).strip().upper()

        # Live price card — shown as soon as we have a valid ticker
        _live_quote = None
        _live_price  = None
        if nt_ticker_raw:
            with st.spinner(f"Fetching {nt_ticker_raw}…"):
                _live_quote = prices.get_quote(nt_ticker_raw)

            if _live_quote:
                _live_price = _live_quote["price"]
                _chg_color  = "#00d4aa" if _live_quote["change"] >= 0 else "#ff6b6b"
                _chg_sign   = "+" if _live_quote["change"] >= 0 else ""
                _mcap       = (
                    f"${_live_quote['market_cap']/1e9:.1f}B"
                    if _live_quote.get("market_cap") else "--"
                )
                st.markdown(f"""
                <div style="background:#13151f;border:1px solid #2a2d3a;border-radius:10px;
                            padding:12px 18px;margin:6px 0 10px 0">
                    <span style="font-family:'JetBrains Mono',monospace;font-size:1rem;font-weight:700;color:#e2e8f0">
                        {_live_quote['ticker']}
                    </span>
                    <span style="color:#6b7185;font-size:0.82rem;margin-left:10px">{_live_quote['name']}</span>
                    &nbsp;&nbsp;
                    <span style="font-family:'JetBrains Mono',monospace;font-size:1.25rem;font-weight:700;color:#e2e8f0">
                        ${_live_quote['price']:.2f}
                    </span>
                    <span style="font-family:'JetBrains Mono',monospace;font-size:0.88rem;font-weight:600;
                                color:{_chg_color};margin-left:10px">
                        {_chg_sign}{_live_quote['change']:.2f} ({_chg_sign}{_live_quote['change_pct']:.2f}%)
                    </span>
                    <br>
                    <span style="font-size:0.73rem;color:#6b7185">
                        Prev Close ${_live_quote['prev_close']:.2f} &nbsp;·&nbsp;
                        Mkt Cap {_mcap} &nbsp;·&nbsp;
                        {_live_quote.get('sector','')}
                    </span>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.warning(f"Could not find a quote for **{nt_ticker_raw}**. Check the ticker and try again.")

        # ── Rest of the form ─────────────────────────────────────────────────
        with st.form("new_trade_form", clear_on_submit=True):
            # Stash the ticker value so the form can read it
            ticker = nt_ticker_raw

            st.markdown('<div class="section-header">Position Details</div>', unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            direction   = c1.selectbox("Direction", ["LONG", "SHORT"])
            _default_ep = float(_live_price) if _live_price else 0.01
            entry_price = c2.number_input(
                "Entry Price *",
                min_value=0.01, step=0.01, format="%.2f",
                value=_default_ep,
            )
            shares = c3.number_input("Shares *", min_value=1, step=1)

            st.markdown('<div class="section-header" style="margin-top:0.5rem">Risk Management</div>', unsafe_allow_html=True)
            r1, r2, r3, r4 = st.columns(4)
            stop_loss    = r1.number_input("Stop Loss",       min_value=0.0, step=0.01, format="%.2f", value=0.0)
            take_profit  = r2.number_input("Take Profit",     min_value=0.0, step=0.01, format="%.2f", value=0.0)
            trailing_stop = r3.number_input("Trailing Stop %", min_value=0.0, step=0.1,  format="%.1f", value=0.0)
            default_exp  = date.today() + timedelta(days=d["default_exp_days"])
            exp_date     = r4.date_input("Expiration Date", value=default_exp)

            st.markdown('<div class="section-header" style="margin-top:0.5rem">Trade Context</div>', unsafe_allow_html=True)
            _default_company = _live_quote["name"] if _live_quote else ""
            t1, t2 = st.columns(2)
            company      = t1.text_input("Company Name", value=_default_company, placeholder="Apple Inc.")
            source       = t2.selectbox("Source", ["SEC Form 4", "SEDI", "Politician Disclosure", "News", "Other", ""])
            i1, i2       = st.columns(2)
            insider_name = i1.text_input("Insider Name", placeholder="John Doe")
            insider_role = i2.text_input("Insider Role", placeholder="CEO")
            filing_url   = st.text_input("Filing URL", placeholder="https://www.sec.gov/...")
            thesis       = st.text_area("Thesis", placeholder="Why are you taking this trade?", height=80)

            submitted = st.form_submit_button("⚡ ENTER TRADE", use_container_width=True, type="primary")

        if submitted:
            # ── Validation ──────────────────────────────────────────────────
            errors = []
            if not ticker:
                errors.append("Ticker is required.")
            if entry_price <= 0:
                errors.append("Entry price must be > 0.")
            if shares <= 0:
                errors.append("Shares must be > 0.")

            cost_basis       = entry_price * shares
            positions_val    = sum(p["cost_basis"] for p in d["positions"])
            realized_pnl_calc = sum(t["realized_pnl"] for t in d["closed_trades"])
            avail_cash       = d["starting_capital"] - positions_val + realized_pnl_calc
            total_val        = avail_cash + positions_val
            max_pos          = total_val * (d["max_position_pct"] / 100)

            if cost_basis > avail_cash:
                errors.append(f"Insufficient cash. Need {fmt_usd(cost_basis)}, have {fmt_usd(avail_cash)}.")
            if cost_basis > max_pos:
                errors.append(f"Position exceeds {d['max_position_pct']}% max ({fmt_usd(max_pos)}).")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                sl = stop_loss if stop_loss > 0 else (
                    entry_price * (1 - d["default_stop_pct"] / 100) if direction == "LONG"
                    else entry_price * (1 + d["default_stop_pct"] / 100)
                )
                tp = take_profit if take_profit > 0 else (
                    entry_price * (1 + d["default_target_pct"] / 100) if direction == "LONG"
                    else entry_price * (1 - d["default_target_pct"] / 100)
                )

                trade_id = generate_trade_id()
                row = [
                    trade_id, ticker, company, direction, today_str(),
                    entry_price, int(shares), round(cost_basis, 2),
                    entry_price, 0.0, 0.0,
                    round(sl, 2), round(tp, 2),
                    round(trailing_stop, 1) if trailing_stop > 0 else "",
                    exp_date.isoformat(),
                    thesis, source, insider_name, insider_role, filing_url,
                ]
                try:
                    sh.append_row("Open Positions", row)
                    sh.append_row("Trade Log", [
                        timestamp_str(), trade_id, "OPEN", ticker,
                        f"{direction} {int(shares)} shares @ ${entry_price:.2f} | Cost: {fmt_usd(cost_basis)}"
                    ])
                    st.success(f"✅ Opened {direction} {ticker}: {int(shares)} shares @ ${entry_price:.2f} ({fmt_usd(cost_basis)})")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as ex:
                    st.error(f"Failed to write to Google Sheets: {ex}")

    # ── Open Positions Table ─────────────────────────────────────────────────
    st.markdown(f'<div class="section-header">Open Positions <span style="color:#00d4aa">({len(d["positions"])})</span></div>', unsafe_allow_html=True)

    if not d["positions"]:
        st.info("📭 No open positions yet.")
    else:
        for idx, p in enumerate(d["positions"]):
            days_held = (date.today() - date.fromisoformat(p["entry_date"])).days if p["entry_date"] else 0
            exp_days_left = (date.fromisoformat(p["expiration_date"]) - date.today()).days if p["expiration_date"] else None
            pnl_color_pos = "#00d4aa" if p["unrealized_pnl"] >= 0 else "#ff6b6b"

            dir_icon = "▲" if p["direction"] == "LONG" else "▼"
            exp_warn = "⚠️ " if exp_days_left is not None and exp_days_left <= 5 else ""
            exp_text = f"{exp_warn}{p['expiration_date']} ({exp_days_left}d left)" if exp_days_left is not None else p["expiration_date"]

            with st.container():
                header_col, action_col = st.columns([5, 2])
                with header_col:
                    st.markdown(f"""
                    <div style="background:#13151f;border:1px solid #2a2d3a;border-radius:10px;padding:12px 16px;margin-bottom:4px">
                        <span style="font-family:'JetBrains Mono',monospace;font-size:1rem;font-weight:700;color:#e2e8f0">{dir_icon} {p['ticker']}</span>
                        <span style="color:#6b7185;font-size:0.8rem;margin-left:10px">{p['company']}</span>
                        &nbsp;&nbsp;
                        <span style="font-family:'JetBrains Mono',monospace;font-size:0.82rem;color:#9aa0b0">Entry {fmt_usd(p['entry_price'])} · Current {fmt_usd(p['current_price'])} · {int(p['shares'])} shares · Cost {fmt_usd(p['cost_basis'])}</span>
                        &nbsp;&nbsp;
                        <span style="font-family:'JetBrains Mono',monospace;font-size:0.9rem;font-weight:600;color:{pnl_color_pos}">
                            {'+' if p['unrealized_pnl'] >= 0 else ''}{fmt_usd(p['unrealized_pnl'])} ({fmt_pct(p['unrealized_pct'])})
                        </span>
                        <br>
                        <span style="font-size:0.75rem;color:#6b7185">SL {fmt_usd(p['stop_loss'])} · TP {fmt_usd(p['take_profit'])} · Exp {exp_text} · {days_held}d held</span>
                    </div>
                    """, unsafe_allow_html=True)

                with action_col:
                    btn_close, btn_edit = st.columns(2)
                    if btn_close.button("Close", key=f"close_btn_{p['trade_id']}_{idx}", use_container_width=True):
                        st.session_state[f"show_close_{p['trade_id']}"] = True
                        st.session_state[f"show_edit_{p['trade_id']}"] = False
                    if btn_edit.button("Edit", key=f"edit_btn_{p['trade_id']}_{idx}", use_container_width=True):
                        st.session_state[f"show_edit_{p['trade_id']}"] = True
                        st.session_state[f"show_close_{p['trade_id']}"] = False

                # ── Inline Close Form ────────────────────────────────────────
                if st.session_state.get(f"show_close_{p['trade_id']}"):
                    with st.form(f"close_form_{p['trade_id']}_{idx}"):
                        cc1, cc2, cc3, cc4 = st.columns([2, 2, 1, 1])
                        exit_price = cc1.number_input("Exit Price", min_value=0.01, step=0.01, format="%.2f", key=f"ep_{p['trade_id']}")
                        exit_reason = cc2.selectbox("Reason", ["manual", "target hit", "stop hit", "expiration", "thesis invalidated"], key=f"er_{p['trade_id']}")
                        confirm_close = cc3.form_submit_button("✓ Confirm", use_container_width=True, type="primary")
                        cancel_close = cc4.form_submit_button("✗ Cancel", use_container_width=True)

                    if cancel_close:
                        st.session_state[f"show_close_{p['trade_id']}"] = False
                        st.rerun()

                    if confirm_close:
                        if exit_price <= 0:
                            st.error("Enter a valid exit price.")
                        else:
                            ep = float(exit_price)
                            entry_p = p["entry_price"]
                            sh_count = p["shares"]
                            realized = (ep - entry_p) * sh_count if p["direction"] == "LONG" else (entry_p - ep) * sh_count
                            realized_pct_val = (realized / (entry_p * sh_count)) * 100

                            exit_row = [
                                p["trade_id"], p["ticker"], p["company"], p["direction"],
                                p["entry_date"], entry_p, today_str(), ep, sh_count,
                                round(realized, 2), round(realized_pct_val, 2),
                                exit_reason, days_held,
                                p["stop_loss"], p["take_profit"],
                                p["thesis"], p["source"], p["insider_name"], p["insider_role"], p["filing_url"],
                            ]
                            try:
                                sh.append_row("Closed Trades", exit_row)
                                sh.delete_row("Open Positions", idx)
                                sh.append_row("Trade Log", [
                                    timestamp_str(), p["trade_id"], "CLOSE", p["ticker"],
                                    f"{exit_reason} | Exit @ ${ep:.2f} | PnL: {fmt_usd(realized)} ({fmt_pct(realized_pct_val)}) | {days_held}d"
                                ])
                                pnl_sign_str = "+" if realized >= 0 else ""
                                st.success(f"✅ Closed {p['ticker']}: {pnl_sign_str}{fmt_usd(realized)} ({fmt_pct(realized_pct_val)})")
                                st.session_state[f"show_close_{p['trade_id']}"] = False
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Failed to close trade: {ex}")

                # ── Inline Edit Form ─────────────────────────────────────────
                if st.session_state.get(f"show_edit_{p['trade_id']}"):
                    with st.form(f"edit_form_{p['trade_id']}_{idx}"):
                        ec1, ec2, ec3, ec4, ec5, ec6 = st.columns([2, 2, 1.5, 2, 1, 1])
                        new_sl = ec1.number_input("Stop Loss", value=p["stop_loss"], step=0.01, format="%.2f", key=f"sl_{p['trade_id']}")
                        new_tp = ec2.number_input("Take Profit", value=p["take_profit"], step=0.01, format="%.2f", key=f"tp_{p['trade_id']}")
                        new_trail = ec3.number_input("Trail %", value=p["trailing_stop_pct"] or 0.0, step=0.1, format="%.1f", key=f"tr_{p['trade_id']}")
                        new_exp = ec4.date_input("Expiration", value=date.fromisoformat(p["expiration_date"]) if p["expiration_date"] else date.today(), key=f"ex_{p['trade_id']}")
                        save_edit = ec5.form_submit_button("✓ Save", use_container_width=True, type="primary")
                        cancel_edit = ec6.form_submit_button("✗ Cancel", use_container_width=True)

                    if cancel_edit:
                        st.session_state[f"show_edit_{p['trade_id']}"] = False
                        st.rerun()

                    if save_edit:
                        # Build updated row (20 columns)
                        updated = [
                            p["trade_id"], p["ticker"], p["company"], p["direction"],
                            p["entry_date"], p["entry_price"], p["shares"], p["cost_basis"],
                            p["current_price"], p["unrealized_pnl"], p["unrealized_pct"],
                            round(new_sl, 2), round(new_tp, 2),
                            round(new_trail, 1) if new_trail > 0 else "",
                            new_exp.isoformat(),
                            p["thesis"], p["source"], p["insider_name"], p["insider_role"], p["filing_url"],
                        ]
                        try:
                            sh.update_row("Open Positions", idx + 2, updated)
                            changes = f"SL:{fmt_usd(new_sl)} TP:{fmt_usd(new_tp)} Trail:{new_trail}% Exp:{new_exp}"
                            sh.append_row("Trade Log", [timestamp_str(), p["trade_id"], "EDIT", p["ticker"], changes])
                            st.success(f"✅ Updated {p['ticker']} — {changes}")
                            st.session_state[f"show_edit_{p['trade_id']}"] = False
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as ex:
                            st.error(f"Failed to edit trade: {ex}")

    # ── Closed Trades Table ──────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander(f"📋 Closed Trades ({len(d['closed_trades'])})", expanded=False):
        if not d["closed_trades"]:
            st.info("No closed trades yet.")
        else:
            import pandas as pd
            ct_sorted = sorted(d["closed_trades"], key=lambda t: t["exit_date"], reverse=True)
            ct_df = pd.DataFrame([{
                "Ticker": t["ticker"],
                "Dir": "▲ L" if t["direction"] == "LONG" else "▼ S",
                "Entry": fmt_usd(t["entry_price"]),
                "Exit": fmt_usd(t["exit_price"]),
                "PnL $": fmt_usd(t["realized_pnl"]),
                "PnL %": fmt_pct(t["realized_pct"]),
                "Reason": t["exit_reason"],
                "Days": t["days_held"],
                "Date": t["exit_date"],
            } for t in ct_sorted])
            st.dataframe(ct_df, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# RIGHT — Charts & Stats
# ─────────────────────────────────────────────────────────────────────────────

with right:
    # ── Equity Curve ─────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">Equity Curve</div>', unsafe_allow_html=True)

    history = d["history"]
    sc = d["starting_capital"]

    if history:
        dates = [h["date"] for h in history]
        values = [h["total_value"] for h in history]
    else:
        # No history yet — show a flat baseline across a readable date range
        from datetime import timedelta
        today = date.today()
        dates = [
            (today - timedelta(days=1)).isoformat(),
            today.isoformat(),
        ]
        values = [sc, sc]

    fig_equity = go.Figure()
    fig_equity.add_trace(go.Scatter(
        x=dates, y=values, mode="lines",
        name="Portfolio",
        line=dict(color="#00d4aa", width=2.5),
        fill="tozeroy",
        fillcolor="rgba(0,212,170,0.07)",
    ))
    fig_equity.add_trace(go.Scatter(
        x=dates, y=[sc] * len(dates), mode="lines",
        name="Starting Capital",
        line=dict(color="rgba(255,255,255,0.15)", width=1, dash="dash"),
    ))
    fig_equity.update_layout(
        paper_bgcolor="#13151f", plot_bgcolor="#13151f",
        margin=dict(l=0, r=0, t=10, b=0), height=220,
        showlegend=False,
        xaxis=dict(gridcolor="#1e2130", tickfont=dict(color="#6b7185", size=10), showline=False),
        yaxis=dict(gridcolor="#1e2130", tickfont=dict(color="#6b7185", size=10),
                   tickformat="$,.0f", showline=False),
        hovermode="x unified",
    )
    st.plotly_chart(fig_equity, use_container_width=True, config={"displayModeBar": False})

    # ── Performance Stats ─────────────────────────────────────────────────────
    st.markdown('<div class="section-header">Performance Stats</div>', unsafe_allow_html=True)

    pf_str = "∞" if d["profit_factor"] == float("inf") else (f"{d['profit_factor']:.2f}" if d["profit_factor"] > 0 else "--")
    best = d["best_trade"]
    worst = d["worst_trade"]

    s1, s2 = st.columns(2)
    with s1:
        sub_color = "#00d4aa" if d["total_pnl"] >= 0 else "#ff6b6b"
        st.metric("Total PnL", fmt_usd(d["total_pnl"]), delta=fmt_pct(d["total_pnl_pct"]))
        st.metric("Win Rate", f"{d['win_rate']:.1f}%" if d["closed_trades"] else "--",
                  delta=f"{d['wins']}W / {d['losses']}L" if d["closed_trades"] else None)
        st.metric("Avg Win", fmt_usd(d["avg_win"]) if d["wins"] else "--")
        st.metric("Best Trade", f"{best['ticker']} {fmt_usd(best['realized_pnl'])}" if best else "--")
        st.metric("Avg Days Held", f"{d['avg_days']:.1f}d" if d["closed_trades"] else "--")
    with s2:
        st.metric("Total Return", fmt_pct(d["total_pnl_pct"]))
        st.metric("Profit Factor", pf_str)
        st.metric("Avg Loss", f"-{fmt_usd(d['avg_loss'])}" if d["losses"] else "--")
        st.metric("Worst Trade", f"{worst['ticker']} {fmt_usd(worst['realized_pnl'])}" if worst else "--")
        st.metric("Total Trades", len(d["closed_trades"]))

    # ── Exit Reason Chart ─────────────────────────────────────────────────────
    st.markdown('<div class="section-header" style="margin-top:1rem">Exit Reasons</div>', unsafe_allow_html=True)

    if d["closed_trades"]:
        from collections import Counter
        counts = Counter(t["exit_reason"] or "manual" for t in d["closed_trades"])
        fig_exit = go.Figure(go.Pie(
            labels=list(counts.keys()),
            values=list(counts.values()),
            hole=0.65,
            marker=dict(colors=["#00d4aa", "#ff6b6b", "#ffa726", "#5b9cf6", "#b18cfe", "#ff9cda"],
                        line=dict(color="#13151f", width=2)),
        ))
        fig_exit.update_layout(
            paper_bgcolor="#13151f", plot_bgcolor="#13151f",
            margin=dict(l=0, r=0, t=10, b=0), height=200,
            legend=dict(font=dict(color="#9aa0b0", size=10), bgcolor="rgba(0,0,0,0)"),
            showlegend=True,
        )
        st.plotly_chart(fig_exit, use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("No closed trades to chart yet.")

    # ── Sheet Link ───────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        "📊 [View Google Sheet ↗](https://docs.google.com/spreadsheets/d/10_2yzOFxMic_lBAJLHwLEkg_1N8lqoQBEpNSUMRfef4/edit)",
        unsafe_allow_html=False,
    )
