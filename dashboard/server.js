const express = require('express');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = 3000;
const DATA_DIR = path.join(__dirname, '..', 'trade_monitor', 'data');

// Serve static files
app.use(express.static(path.join(__dirname, 'public')));

/**
 * Safely read a JSON file, returning a fallback if missing or malformed.
 */
function readJSON(filename, fallback = null) {
  const filepath = path.join(DATA_DIR, filename);
  try {
    if (!fs.existsSync(filepath)) return fallback;
    const raw = fs.readFileSync(filepath, 'utf8').trim();
    if (!raw) return fallback;
    return JSON.parse(raw);
  } catch (err) {
    console.error(`Error reading ${filename}:`, err.message);
    return fallback;
  }
}

// ---------- API Endpoints ----------

// GET /api/state
app.get('/api/state', (req, res) => {
  const state = readJSON('state.json', {
    last_poll_time: null,
    experiment_day: null,
    experiment_total_days: 90,
    source_status: { SEC_EDGAR: 'N/A', SEDI: 'N/A', POLITICIAN: 'N/A' },
    errors_today: 0,
    total_filings_detected: 0,
    total_signals_generated: 0,
    uptime_start: null
  });
  res.json(state);
});

// GET /api/portfolio
app.get('/api/portfolio', (req, res) => {
  const portfolio = readJSON('portfolio.json', {
    cash: 0,
    positions: [],
    closed_positions: [],
    orders: []
  });
  res.json(portfolio);
});

// GET /api/signals (last 50)
app.get('/api/signals', (req, res) => {
  const signals = readJSON('signals.json', []);
  const arr = Array.isArray(signals) ? signals : [];
  res.json(arr.slice(-50).reverse());
});

// GET /api/filings (last 50)
app.get('/api/filings', (req, res) => {
  const filings = readJSON('filings.json', []);
  const arr = Array.isArray(filings) ? filings : [];
  res.json(arr.slice(-50).reverse());
});

// GET /api/notifications
app.get('/api/notifications', (req, res) => {
  const notifications = readJSON('notifications.json', []);
  const arr = Array.isArray(notifications) ? notifications : [];
  res.json(arr.slice(-20).reverse());
});

// GET /api/market
app.get('/api/market', (req, res) => {
  const cache = readJSON('market_cache.json', {});
  res.json(cache);
});

// GET /api/summary — computed KPIs
app.get('/api/summary', (req, res) => {
  const portfolio = readJSON('portfolio.json', { cash: 0, positions: [], closed_positions: [], orders: [] });
  const signals = readJSON('signals.json', []);
  const state = readJSON('state.json', {});
  const market = readJSON('market_cache.json', {});

  const positions = portfolio.positions || [];
  const closedPositions = portfolio.closed_positions || [];
  const signalsArr = Array.isArray(signals) ? signals : [];
  const cash = portfolio.cash || 0;

  // Calculate positions value using market prices when available
  let positionsValue = 0;
  const enrichedPositions = positions.map(p => {
    const marketData = market[p.ticker];
    const currentPrice = (marketData && marketData.data && marketData.data.price) || p.current_price || p.entry_price;
    const value = currentPrice * (p.shares || 0);
    const unrealizedPnl = (currentPrice - p.entry_price) * (p.shares || 0);
    const unrealizedPnlPct = p.entry_price ? ((currentPrice - p.entry_price) / p.entry_price) * 100 : 0;
    positionsValue += value;
    return {
      ...p,
      current_price: currentPrice,
      unrealized_pnl: unrealizedPnl,
      unrealized_pnl_pct: unrealizedPnlPct
    };
  });

  const totalValue = cash + positionsValue;
  const initialCapital = 100000; // assumed starting capital
  const totalPnl = totalValue - initialCapital;
  const totalPnlPct = ((totalValue - initialCapital) / initialCapital) * 100;

  // Win rate from closed positions
  const wins = closedPositions.filter(p => (p.realized_pnl || 0) > 0);
  const losses = closedPositions.filter(p => (p.realized_pnl || 0) <= 0);
  const winRate = closedPositions.length > 0 ? (wins.length / closedPositions.length) * 100 : 0;

  const avgWin = wins.length > 0 ? wins.reduce((s, p) => s + (p.realized_pnl || 0), 0) / wins.length : 0;
  const avgLoss = losses.length > 0 ? Math.abs(losses.reduce((s, p) => s + (p.realized_pnl || 0), 0) / losses.length) : 0;
  const profitFactor = avgLoss > 0 ? (avgWin * wins.length) / (avgLoss * losses.length) : wins.length > 0 ? Infinity : 0;

  // Exit rules breakdown
  const exitRules = {};
  closedPositions.forEach(p => {
    const rule = p.exit_rule || 'unknown';
    if (!exitRules[rule]) exitRules[rule] = { count: 0, pnl: 0 };
    exitRules[rule].count++;
    exitRules[rule].pnl += (p.realized_pnl || 0);
  });

  // Signals today
  const today = new Date().toISOString().slice(0, 10);
  const signalsToday = signalsArr.filter(s => {
    const ts = s.created_at || s.timestamp || '';
    return ts.slice(0, 10) === today;
  }).length;

  // Open positions count
  const openPositions = positions.filter(p => p.status === 'open').length;

  res.json({
    total_value: totalValue,
    cash: cash,
    positions_value: positionsValue,
    total_pnl: totalPnl,
    total_pnl_pct: totalPnlPct,
    open_positions: openPositions,
    signals_today: signalsToday,
    win_rate: winRate,
    closed_trades: closedPositions.length,
    wins: wins.length,
    losses: losses.length,
    avg_win: avgWin,
    avg_loss: avgLoss,
    profit_factor: profitFactor,
    exit_rules: exitRules,
    enriched_positions: enrichedPositions
  });
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Trade Monitor Dashboard running at http://0.0.0.0:${PORT}`);
});
