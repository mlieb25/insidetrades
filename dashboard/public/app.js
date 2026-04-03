/* ============================================================
   INSIDER TRADE MONITOR — Frontend Application
   Auto-refreshes every 30 seconds
   ============================================================ */

const REFRESH_INTERVAL = 30; // seconds
let countdown = REFRESH_INTERVAL;
let refreshTimer = null;

// ========== Helpers ==========

function $(id) { return document.getElementById(id); }

function fmt(n, decimals = 2) {
  if (n == null || isNaN(n)) return '—';
  return Number(n).toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  });
}

function fmtMoney(n, decimals = 2) {
  if (n == null || isNaN(n)) return '$0.00';
  const prefix = n < 0 ? '-$' : '$';
  return prefix + fmt(Math.abs(n), decimals);
}

function fmtPct(n, decimals = 2) {
  if (n == null || isNaN(n)) return '—';
  return (n >= 0 ? '+' : '') + fmt(n, decimals) + '%';
}

function pnlClass(n) {
  if (n > 0) return 'positive';
  if (n < 0) return 'negative';
  return 'neutral';
}

function timeAgo(dateStr) {
  if (!dateStr) return '';
  const now = new Date();
  const then = new Date(dateStr);
  const diffMs = now - then;
  if (isNaN(diffMs)) return '';
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return mins + 'm ago';
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return hrs + 'h ago';
  const days = Math.floor(hrs / 24);
  return days + 'd ago';
}

function shortTime(dateStr) {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
  } catch { return '—'; }
}

function shortDate(dateStr) {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' +
           d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
  } catch { return '—'; }
}

function daysBetween(d1, d2) {
  const ms = new Date(d2) - new Date(d1);
  return Math.max(0, Math.floor(ms / 86400000));
}

function classificationBadge(cls) {
  const c = (cls || '').toUpperCase();
  if (c === 'REPLICATE') return '<span class="badge badge--replicate">REPLICATE</span>';
  if (c === 'WATCHLIST') return '<span class="badge badge--watchlist">WATCHLIST</span>';
  if (c === 'REJECT') return '<span class="badge badge--reject">REJECT</span>';
  if (c === 'SKIP') return '<span class="badge badge--skip">SKIP</span>';
  return '<span class="badge badge--reject">' + (cls || '—') + '</span>';
}

function directionBadge(dir) {
  const d = (dir || '').toUpperCase();
  if (d === 'LONG') return '<span class="badge--long">LONG</span>';
  if (d === 'SHORT') return '<span class="badge--short">SHORT</span>';
  return dir || '—';
}

function scoreBar(score, max = 100) {
  const pct = Math.min(100, Math.max(0, (score / max) * 100));
  let color = 'var(--teal)';
  if (pct < 40) color = 'var(--coral)';
  else if (pct < 65) color = 'var(--amber)';
  return `<span class="score-bar">
    <span class="mono">${fmt(score, 1)}</span>
    <span class="score-bar__fill"><span class="score-bar__inner" style="width:${pct}%;background:${color}"></span></span>
  </span>`;
}

function txnAction(code) {
  const c = (code || '').toUpperCase();
  if (c === 'P' || c === 'BUY' || c === 'A') return { label: 'BUY', cls: 'filing-item__action--buy' };
  if (c === 'S' || c === 'SELL' || c === 'D' || c === 'F') return { label: 'SELL', cls: 'filing-item__action--sell' };
  return { label: code || '—', cls: 'filing-item__action--other' };
}

// ========== API Fetch ==========

async function fetchJSON(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    return await res.json();
  } catch { return null; }
}

// ========== Render Functions ==========

function renderState(state) {
  if (!state) return;

  // Experiment day
  const day = state.experiment_day || '—';
  const total = state.experiment_total_days || 90;
  $('experimentDay').textContent = `Day ${day}/${total}`;

  // Last poll
  if (state.last_poll_time) {
    $('lastPoll').textContent = shortDate(state.last_poll_time);
    $('pollAge').textContent = timeAgo(state.last_poll_time);
    
    // Check staleness (>5 min = warning)
    const age = Date.now() - new Date(state.last_poll_time).getTime();
    if (age > 300000) {
      $('pollAge').style.color = 'var(--amber)';
    } else {
      $('pollAge').style.color = '';
    }
  }

  // Source status
  const sources = state.source_status || {};
  const badgesHTML = Object.entries(sources).map(([name, status]) => {
    let cls = 'source-badge--na';
    if (status === 'OK' || status === 'ACTIVE') cls = 'source-badge--ok';
    else if (status === 'ERROR' || status === 'FAIL') cls = 'source-badge--error';
    return `<span class="source-badge ${cls}">${name}: ${status}</span>`;
  }).join('');
  
  if (badgesHTML) {
    $('sourceBadges').innerHTML = badgesHTML;
  }

  // Status dot
  const errorsToday = state.errors_today || 0;
  const dot = $('statusDot');
  if (errorsToday > 5) {
    dot.classList.add('status-dot--error');
    dot.title = `${errorsToday} errors today`;
  } else {
    dot.classList.remove('status-dot--error');
    dot.title = 'System healthy';
  }

  // Bottom bar
  $('errorsToday').textContent = errorsToday;
  $('totalFilings').textContent = state.total_filings_detected || 0;
  $('totalSignals').textContent = state.total_signals_generated || 0;
}

function renderSummary(summary) {
  if (!summary) return;

  // KPI cards
  $('kpiTotalValue').textContent = fmtMoney(summary.total_value);
  
  const pnlEl = $('kpiPnl');
  pnlEl.textContent = `${fmtMoney(summary.total_pnl)} (${fmtPct(summary.total_pnl_pct)})`;
  pnlEl.className = 'kpi-card__delta ' + pnlClass(summary.total_pnl);

  $('kpiOpenPositions').textContent = summary.open_positions || 0;
  $('kpiPositionsValue').textContent = fmtMoney(summary.positions_value) + ' invested';

  $('kpiSignalsToday').textContent = summary.signals_today || 0;
  $('kpiTotalSignals').textContent = (summary.closed_trades + summary.open_positions || 0) + ' total trades';

  if (summary.closed_trades > 0) {
    $('kpiWinRate').textContent = fmt(summary.win_rate, 1) + '%';
  } else {
    $('kpiWinRate').textContent = '—';
  }
  $('kpiClosedTrades').textContent = (summary.closed_trades || 0) + ' closed trades';

  // Performance summary
  $('perfClosed').textContent = summary.closed_trades || 0;
  $('perfWinRate').textContent = summary.closed_trades > 0 ? fmt(summary.win_rate, 1) + '%' : '—';
  
  const avgWinEl = $('perfAvgWin');
  avgWinEl.textContent = fmtMoney(summary.avg_win);
  avgWinEl.className = 'perf-stat__value mono ' + (summary.avg_win > 0 ? 'positive' : 'neutral');

  const avgLossEl = $('perfAvgLoss');
  avgLossEl.textContent = '-' + fmtMoney(summary.avg_loss);
  avgLossEl.className = 'perf-stat__value mono ' + (summary.avg_loss > 0 ? 'negative' : 'neutral');

  $('perfProfitFactor').textContent = summary.profit_factor === Infinity ? '∞' : fmt(summary.profit_factor, 2);

  const totalPnlEl = $('perfTotalPnl');
  totalPnlEl.textContent = fmtMoney(summary.total_pnl);
  totalPnlEl.className = 'perf-stat__value mono ' + pnlClass(summary.total_pnl);

  // Exit rules
  renderExitRules(summary.exit_rules || {});

  // Open positions
  renderPositions(summary.enriched_positions || []);

  // Unrealized PnL badge
  const totalUnrealized = (summary.enriched_positions || []).reduce((s, p) => s + (p.unrealized_pnl || 0), 0);
  const unrealizedEl = $('unrealizedPnl');
  unrealizedEl.textContent = fmtMoney(totalUnrealized);
  unrealizedEl.className = 'panel__badge mono ' + pnlClass(totalUnrealized);

  // Portfolio allocation
  renderAllocation(summary.cash, summary.positions_value, summary.total_value);
}

function renderPositions(positions) {
  const tbody = $('positionsBody');
  const open = positions.filter(p => p.status === 'open');

  if (open.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9" class="empty-state">No open positions</td></tr>';
    return;
  }

  tbody.innerHTML = open.map(p => {
    const daysHeld = daysBetween(p.opened_at, new Date().toISOString());
    return `<tr>
      <td><strong>${p.ticker}</strong></td>
      <td>${directionBadge(p.direction)}</td>
      <td>${fmtMoney(p.entry_price)}</td>
      <td>${fmtMoney(p.current_price)}</td>
      <td class="${pnlClass(p.unrealized_pnl)}">${fmtMoney(p.unrealized_pnl)}</td>
      <td class="${pnlClass(p.unrealized_pnl_pct)}">${fmtPct(p.unrealized_pnl_pct)}</td>
      <td style="color:var(--coral)">${fmtMoney(p.stop_price)}</td>
      <td style="color:var(--teal)">${fmtMoney(p.target_price)}</td>
      <td>${daysHeld}d</td>
    </tr>`;
  }).join('');
}

function renderSignals(signals) {
  const tbody = $('signalsBody');
  $('signalCount').textContent = signals.length;

  if (!signals || signals.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No signals yet</td></tr>';
    return;
  }

  // Show last 20
  const recent = signals.slice(0, 20);
  tbody.innerHTML = recent.map(s => {
    const time = shortTime(s.created_at || s.timestamp);
    const conf = s.confidence != null ? fmt(s.confidence * 100, 0) + '%' : '—';
    return `<tr>
      <td>${time}</td>
      <td><strong>${s.ticker || '—'}</strong></td>
      <td>${directionBadge(s.direction)}</td>
      <td>${scoreBar(s.score || 0)}</td>
      <td>${conf}</td>
      <td>${classificationBadge(s.classification)}</td>
      <td>${s.status || '—'}</td>
    </tr>`;
  }).join('');
}

function renderFilings(filings) {
  const feed = $('filingsFeed');
  $('filingCount').textContent = filings.length;

  if (!filings || filings.length === 0) {
    feed.innerHTML = '<div class="empty-state">No filings detected yet</div>';
    return;
  }

  feed.innerHTML = filings.slice(0, 50).map(f => {
    const time = shortDate(f.filing_date || f.period_of_report || f.accepted_date);
    const action = txnAction(f.transaction_code || f.type);
    const shares = f.shares ? Number(f.shares).toLocaleString() : '—';
    const price = f.price ? fmtMoney(f.price) : '';
    const value = (f.shares && f.price) ? fmtMoney(f.shares * f.price, 0) : '—';
    
    return `<div class="filing-item">
      <span class="filing-item__time">${time}</span>
      <span class="filing-item__info">
        <span class="filing-item__ticker">${f.ticker || '—'}</span>
        <span class="filing-item__name">${f.owner_name || f.insider_name || '—'}</span>
        <span class="filing-item__action ${action.cls}">${action.label}</span>
      </span>
      <span class="filing-item__value">${value}</span>
    </div>`;
  }).join('');
}

function renderExitRules(exitRules) {
  const tbody = $('exitRulesBody');
  const entries = Object.entries(exitRules);

  if (entries.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3" class="empty-state">No closed trades yet</td></tr>';
    return;
  }

  tbody.innerHTML = entries.map(([rule, data]) => {
    return `<tr>
      <td>${rule}</td>
      <td>${data.count}</td>
      <td class="${pnlClass(data.pnl)}">${fmtMoney(data.pnl)}</td>
    </tr>`;
  }).join('');
}

function renderAllocation(cash, positionsValue, total) {
  if (!total || total === 0) {
    $('allocCashBar').style.width = '100%';
    $('allocPosBar').style.width = '0%';
    $('allocCash').textContent = '$0';
    $('allocPos').textContent = '$0';
    $('allocCashPct').textContent = '0%';
    $('allocPosPct').textContent = '0%';
    return;
  }

  const cashPct = (cash / total) * 100;
  const posPct = (positionsValue / total) * 100;

  $('allocCashBar').style.width = cashPct + '%';
  $('allocPosBar').style.width = posPct + '%';
  $('allocCash').textContent = fmtMoney(cash, 0);
  $('allocPos').textContent = fmtMoney(positionsValue, 0);
  $('allocCashPct').textContent = fmt(cashPct, 1) + '%';
  $('allocPosPct').textContent = fmt(posPct, 1) + '%';
}

// ========== Data Refresh ==========

async function refreshAll() {
  const [state, summary, signals, filings] = await Promise.all([
    fetchJSON('/api/state'),
    fetchJSON('/api/summary'),
    fetchJSON('/api/signals'),
    fetchJSON('/api/filings')
  ]);

  renderState(state);
  renderSummary(summary);
  renderSignals(signals || []);
  renderFilings(filings || []);

  // Reset countdown
  countdown = REFRESH_INTERVAL;
}

function startCountdown() {
  if (refreshTimer) clearInterval(refreshTimer);
  
  refreshTimer = setInterval(() => {
    countdown--;
    const el = $('refreshCountdown');
    if (el) el.textContent = countdown + 's';

    if (countdown <= 0) {
      refreshAll();
    }
  }, 1000);
}

// ========== Init ==========

document.addEventListener('DOMContentLoaded', () => {
  refreshAll();
  startCountdown();
});
