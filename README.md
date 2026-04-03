# Insider Trade Monitor

Autonomous SEC Form 4 insider trade detection, scoring, and paper-trading system.

## What It Does

1. **Detects** new SEC Form 4 filings within minutes of public disclosure via EDGAR feeds
2. **Parses** each filing to extract insider identity, role, transaction type, size, and price
3. **Scores** every trade on a 100-point model (freshness, seniority, size, cluster, price gap, liquidity, market regime)
4. **Generates signals** for high-conviction open-market insider purchases (score ≥ 65)
5. **Executes paper trades** with position sizing, stop losses, profit targets, and trailing stops
6. **Sends alerts** via Gmail API and push notifications
7. **Tracks performance** with structured logs, a portfolio journal, and a live dashboard

## Architecture

```
SEC EDGAR Atom Feed → Poller → Parser → Scorer → Portfolio → Gmail API
     (hourly)          │         │         │         │          │
                       ▼         ▼         ▼         ▼          ▼
                  filings.json  trades  signals   portfolio  Email Alert
                                parsed  .json     .json      + Push
```

## Setup

```bash
# Clone
git clone https://github.com/mlieb25/insidetrades.git
cd insidetrades

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Place your GCP service account JSON at credentials/service_account.json

# Test the pipeline
python -m trade_monitor.test_pipeline

# Run one poll cycle
python -m trade_monitor.run_cycle poll

# Run health check
python -m trade_monitor.run_cycle health
```

## Scoring Model (0–100)

| Factor | Max | Top Score For |
|--------|-----|---------------|
| Filing Freshness | 15 | Detected within 2 hours |
| Insider Seniority | 20 | CEO / Chairman |
| Transaction Type | 15 | Open-market purchase (code P) |
| Dollar Size | 15 | > $5M trade value |
| Cluster Buying | 10 | 3+ insiders buying same ticker |
| Price Gap | 10 | Current price within 2% of insider price |
| Liquidity | 5 | Market cap > $10B |
| Market Regime | 10 | Insider buying near 52-week low |

**Thresholds:** ≥80 = HIGH conviction (5% position), 65-79 = MEDIUM (2.5%), 50-64 = watchlist, <50 = reject.

## Exit Rules

| Rule | Trigger |
|------|---------|
| Event Stop | Halt, contradictory filing, or earnings within 2 days |
| Price Stop | ATR-based stop loss (2× ATR below entry) |
| Profit Target | 3× ATR above entry |
| Trailing Stop | Activates at 1.5× ATR profit, trails by 1× ATR |
| Time Stop | Max holding period (10/30/60 days by conviction) |

## Cron Schedule (PDT)

| Task | When | What |
|------|------|------|
| Hourly Poll | Mon–Fri 6AM–3PM | EDGAR polling + scoring + alerts |
| Daily Digest | Mon–Fri 1:30PM | Portfolio summary email |
| Weekly Summary | Fridays 2:00PM | Performance report |

## Project Structure

```
trade_monitor/
├── config.py           # All constants and thresholds
├── models.py           # Data classes (Filing, InsiderTrade, TradeSignal, Position)
├── edgar_poller.py     # SEC EDGAR Atom feed + EFTS batch search
├── scorer.py           # 8-factor scoring engine
├── portfolio.py        # Paper portfolio management
├── exit_manager.py     # 5 exit rule frameworks
├── market_data.py      # Market data cache
├── gmail_sender.py     # Gmail API via GCP service account
├── notifier.py         # Alert / digest / summary formatters
├── politician_tracker.py # STOCK Act trade tracker
├── logger.py           # Structured JSON logging
├── state.py            # Crash-safe atomic persistence
├── main.py             # Orchestrator
├── cron_poll.py        # Hourly cron runner
├── cron_digest.py      # Daily/weekly digest runner
├── run_cycle.py        # Manual single-cycle runner
├── test_pipeline.py    # End-to-end test
├── credentials/        # GCP service account (git-ignored)
├── data/               # Runtime state JSON files
└── logs/               # Structured logs + journal
```

## Dashboard

The `trade_dashboard/` directory contains an Express.js + vanilla JS monitoring dashboard. Run with:

```bash
cd trade_dashboard
npm install
node server.js
# Open http://localhost:3000
```

## Legal

- Paper trading only — no live orders unless explicitly enabled
- Uses only publicly disclosed SEC filings
- Rate-limited to comply with EDGAR terms (10 req/sec, identified User-Agent)
- Does not use or seek material non-public information
