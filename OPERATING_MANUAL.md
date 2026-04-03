# Autonomous Trade Monitor — Operating Manual

## System Overview

A 24/7 autonomous agent that detects SEC Form 4 insider trades within minutes of public disclosure, scores each trade on a 100-point model, generates paper-trading signals, and sends immediate notifications.

**Experiment Window:** April 2, 2026 → July 2, 2026 (90 days)
**Mode:** PAPER TRADING (no real orders)
**Starting Capital:** $100,000

---

## Architecture

```
SEC EDGAR Atom Feed ──→ Poller ──→ Parser ──→ Scorer ──→ Portfolio ──→ Notifier
(every 60 min)          │           │           │           │           │
                        ▼           ▼           ▼           ▼           ▼
                   filings.json  trades    signals.json  portfolio.json  Email
                                 parsed                                  Push
                                                                     Notification
```

### Data Sources (Priority Order)

| Source | Priority | Lag | Method | Frequency |
|--------|----------|-----|--------|-----------|
| SEC EDGAR Form 4 | HIGHEST | <2 days | Atom feed polling | Hourly |
| Canadian SEDI | MEDIUM | ~days | Browser automation | Every 4 hours |
| U.S. Politicians | LOW | 30-45 days | Finance API | Daily |

### File Structure

```
trade_monitor/
├── config.py             # All configuration constants
├── models.py             # Data classes (Filing, InsiderTrade, TradeSignal, Position)
├── edgar_poller.py       # SEC EDGAR Atom feed + EFTS search
├── scorer.py             # 0-100 scoring engine with 8 factors
├── portfolio.py          # Paper portfolio: sizing, orders, PnL
├── exit_manager.py       # 5 exit rule frameworks
├── notifier.py           # Alert, digest, summary formatters
├── market_data.py        # Market data cache layer
├── politician_tracker.py # STOCK Act trade tracker
├── logger.py             # Structured JSON logging + journal
├── state.py              # Crash-safe persistence (atomic writes)
├── main.py               # Orchestrator (poll_cycle, digest, summary, health)
├── cron_poll.py           # Hourly cron runner
├── cron_digest.py         # Daily/weekly digest cron runner
├── run_cycle.py           # Standalone single-cycle runner
├── test_pipeline.py       # End-to-end test script
├── data/                  # Persisted state (JSON files)
│   ├── state.json
│   ├── seen_accessions.json
│   ├── portfolio.json
│   ├── signals.json
│   ├── filings.json
│   ├── notifications.json
│   └── market_cache.json
└── logs/
    ├── system.log
    ├── filings.log
    ├── signals.log
    ├── trades.log
    ├── errors.log
    └── journal.md
```

---

## Scoring Model (0–100)

| Factor | Weight | Criteria |
|--------|--------|----------|
| Filing Freshness | 0-15 | 0-2h=15, 2-6h=12, 6-12h=8, 12-24h=4, 24-48h=2, >48h=0 |
| Insider Seniority | 0-20 | CEO/Chair=20, CFO/COO=17, C-suite=14, Director=12, VP=10, 10%=8, Other=5 |
| Transaction Type | 0-15 | Open-market purchase (P)=15, Sale (S)=10, Others=0 (reject) |
| Dollar Size | 0-15 | >$5M=15, >$1M=12, >$500K=10, >$100K=7, >$50K=5 |
| Cluster Buying | 0-10 | 3+ insiders=10, 2=7, 1=3 |
| Price Gap | 0-10 | ≤2%=10, 2-5%=7, 5-10%=4, >10%=0, >15%=reject |
| Liquidity | 0-5 | >$10B=5, >$2B=4, >$500M=3, <$500M=reject |
| Market Regime | 0-10 | Insider buy near 52w low=10, mid=5, near high=3 |

### Classification Thresholds

| Score | Classification | Action |
|-------|---------------|--------|
| ≥ 80 | HIGH conviction | Full position (5% capital), 60-day hold |
| 65-79 | MEDIUM conviction | Half position (2.5%), 30-day hold |
| 50-64 | WATCHLIST | Monitor, no trade |
| < 50 | REJECT | Logged and dismissed |

### Rejection Criteria (Automatic)
- Transaction code not P or S
- Dollar value < $50,000
- Market cap < $500M
- Price moved >15% above insider price
- Filing lag > 72 hours

---

## Exit Rules

| Rule | Trigger | Priority |
|------|---------|----------|
| Event Stop (Halt) | Stock halted | 1 (highest) |
| Event Stop (Filing) | Contradictory insider filing detected | 2 |
| Event Stop (Earnings) | Earnings within 2 trading days | 3 |
| Price Stop | Price hits ATR-based stop loss (2× ATR) | 4 |
| Profit Target | Price hits target (3× ATR above entry) | 5 |
| Trailing Stop | After 1.5× ATR profit, trail by 1× ATR | 6 |
| Time Stop | Max holding period exceeded (10/30/60 days) | 7 |

---

## Position Sizing

- **Per-trade max:** 5% of portfolio (HIGH), 2.5% (MEDIUM)
- **Total exposure max:** 30% of portfolio
- **Slippage assumptions:**
  - Large cap (>$10B): 0.10%
  - Mid cap ($2-10B): 0.25%
  - Small cap ($500M-$2B): 0.50%

---

## Notification Templates

### Signal Alert
Sent immediately when a qualifying signal (score ≥ 65) is generated:
- Ticker and company name
- Direction (LONG/SHORT)
- Score and confidence
- Insider identity, role, and trade details
- Entry zone, stop loss, profit target
- All timestamps (trade date, filing date, detection time, alert time)
- Link to original SEC filing

### Daily Digest (4:30 PM ET)
- Portfolio value and PnL
- New signals generated today
- Positions closed today
- System health metrics

### Weekly Summary (Fridays 5 PM ET)
- Week number and cumulative PnL
- Win rate, profit factor, best/worst trades
- Exit rule breakdown
- Signal generation statistics

---

## Cron Schedule

| Task | UTC Cron | Local (PDT) | Description |
|------|----------|-------------|-------------|
| Poll Cycle | `0 13,14,15,16,17,18,19,20,21 * * 1-5` | 6AM-2PM PDT hourly | SEC EDGAR polling + scoring |
| Daily Digest | `30 20 * * 1-5` | 1:30 PM PDT | End-of-day summary |
| Weekly Summary | `0 21 * * 5` | 2 PM PDT Fridays | Weekly performance report |

---

## Commands

### Run a single poll cycle manually
```bash
cd /home/user/workspace
python -m trade_monitor.run_cycle poll
```

### Run health check
```bash
python -m trade_monitor.run_cycle health
```

### Run the full test pipeline
```bash
python -m trade_monitor.test_pipeline
```

### View the dashboard
Open http://localhost:3000 when the dashboard server is running.

### Check logs
```bash
cat trade_monitor/logs/journal.md       # Human-readable journal
cat trade_monitor/logs/system.log       # Structured system events
cat trade_monitor/logs/signals.log      # All signal decisions
cat trade_monitor/logs/trades.log       # All trade executions
```

### View current state
```bash
python -c "import json; print(json.dumps(json.load(open('trade_monitor/data/state.json')), indent=2))"
python -c "import json; print(json.dumps(json.load(open('trade_monitor/data/portfolio.json')), indent=2))"
```

---

## Safety & Compliance

- **Paper mode only** — no live trades unless PAPER_MODE is explicitly set to False
- **Public data only** — all sources are publicly accessible government/regulatory filings
- **Rate-limited** — SEC requests capped at 10/second with User-Agent identification
- **Terms-compliant** — uses official EDGAR feeds, not scraping restricted pages
- **Conservative slippage** — assumes worst-case execution prices
- **No MNPI** — system only acts on publicly disclosed, timestamped filings

---

## Monitoring & Recovery

- **State persistence:** All state saved atomically to JSON; survives crashes
- **Deduplication:** Seen accession numbers tracked to prevent duplicate processing
- **Error tracking:** Errors logged to errors.log with full context
- **Heartbeat:** last_heartbeat in state.json updated every cycle
- **Graceful degradation:** If a source is unavailable, others continue operating
- **Journal:** Human-readable decisions log at logs/journal.md

---

## Experiment Plan

### Phase 1: Validation (Days 1-7)
- Verify polling reliability
- Confirm signal scoring produces sensible results
- Check notification delivery
- Tune score threshold if needed

### Phase 2: Active Monitoring (Days 8-60)
- Full autonomous operation
- Track signal quality vs outcomes
- Identify best-performing signal subtypes
- Monitor exit rule effectiveness

### Phase 3: Analysis (Days 61-90)
- Comprehensive performance review
- Compare results by insider role, sector, market cap
- Evaluate each exit rule's contribution
- Determine if strategy has alpha vs benchmark
- Document lessons learned

### Success Metrics
- **Detection latency:** Average time from filing to alert
- **Signal precision:** % of REPLICATE signals that are profitable
- **Win rate:** % of closed positions with positive PnL
- **Profit factor:** Total gross profit / Total gross loss
- **Sharpe ratio approximation:** Annualized return / volatility
