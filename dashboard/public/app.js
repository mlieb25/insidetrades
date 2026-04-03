/* ============================================================
   INSIDER TRADE MONITOR — Frontend Application
   Reads live data from Google Sheets (public CSV export)
   Auto-refreshes every 60 seconds
   ============================================================ */

const SPREADSHEET_ID = '10_2yzOFxMic_lBAJLHwLEkg_1N8lqoQBEpNSUMRfef4';
const REFRESH_INTERVAL = 60; // seconds
let countdown = REFRESH_INTERVAL;
let refreshTimer = null;

// Sheet GIDs — set after first metadata fetch, or use names via CSV export
const SHEET_NAMES = {
  filings: 'Filings',
  signals: 'Signals',
  openPositions: 'Open Positions',
  closedPositions: 'Closed Positions',
  portfolio: 'Portfolio Snapshots',
  system: 'System Log',
};

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

function shortDate(dateStr) {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    if (isNaN(d)) return dateStr.substring(0, 16);
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
  if (c === 'P') return { label: 'BUY', cls: 'filing-item__action--buy' };
  if (c === 'S') return { label: 'SELL', cls: 'filing-item__action--sell' };
  return { label: code || '—', cls: 'filing-item__action--other' };
}

// ========== Google Sheets CSV Fetch ==========

async function fetchSheet(sheetName) {
  const url = `https://docs.google.com/spreadsheets/d/${SPREADSHEET_ID}/gviz/tq?tqx=out:json&sheet=${encodeURIComponent(sheetName)}`;
  try {
    const res = await fetch(url);
    const text = await res.text();
    // Response is wrapped in google.visualization.Query.setResponse({...})
    const jsonStr = text.match(/google\.visualization\.Query\.setResponse\(([\s\S]+)\);?/);
    if (!jsonStr) return [];
    const data = JSON.parse(jsonStr[1]);
    const cols = data.table.cols.map(c => c.label || '');
    const rows = (data.table.rows || []).map(r => {
      const obj = {};
      r.c.forEach((cell, i) => {
        if (cols[i]) {
          obj[cols[i]] = cell ? (cell.v != null ? cell.v : (cell.f || '')) : '';
        }
      });
      return obj;
    });
    return rows;
  } catch (e) {
    console.error(`Failed to fetch sheet "${sheetName}":`, e);
    return [];
  }
}

// ========== Render Functions ==========

function renderState(systemLogs, portfolioSnapshots) {
  // Get latest system log entry
  const latest = systemLogs.length > 0 ? systemLogs[systemLogs.length - 1] : null;
  // Get latest portfolio snapshot
  const latestPort = portfolioSnapshots.length > 0 ? portfolioSnapshots[portfolioSnapshots.length - 1] : null;

  // Experiment day
  const day = latestPort ? (latestPort['Experiment Day'] || '—') : '—';
  $('experimentDay').textContent = `Day ${day}/90`;

  // Last poll
  if (latest && latest['Timestamp']) {
    $('lastPoll').textContent = shortDate(latest['Timestamp']);
    $('pollAge').textContent = timeAgo(latest['Timestamp']);
    const age = Date.now() - new Date(latest['Timestamp']).getTime();
    $('pollAge').style.color = age > 3600000 * 26 ? 'var(--amber)' : '';
  }

  // Source status
  const statusStr = latest ? (latest['Source Status'] || '') : '';
  const badges = [];
  if (statusStr.includes('SEC_EDGAR')) {
    const m = statusStr.match(/SEC_EDGAR['":\s]+(\w+)/);
    badges.push({ name: 'SEC_EDGAR', status: m ? m[1] : 'OK' });
  } else {
    badges.push({ name: 'SEC_EDGAR', status: 'OK' });
  }
  badges.push({ name: 'SEDI', status: 'N/A' });
  badges.push({ name: 'POLITICIAN', status: 'N/A' });

  $('sourceBadges').innerHTML = badges.map(b => {
    let cls = 'source-badge--na';
    if (b.status === 'OK') cls = 'source-badge--ok';
    return `<span class="source-badge ${cls}">${b.name}: ${b.status}</span>`;
  }).join('');

  // Bottom bar
  $('errorsToday').textContent = latest ? (latest['Errors'] || 0) : 0;
  $('totalFilings').textContent = latest ? (latest['Filings Detected'] || 0) : 0;
  $('totalSignals').textContent = latest ? (latest['Signals Generated'] || 0) : 0;
}

function renderSummary(portfolioSnapshots, closedPositions, openPositions) {
  const latest = portfolioSnapshots.length > 0 ? portfolioSnapshots[portfolioSnapshots.length - 1] : {};

  const totalValue = parseFloat(latest['Total Value']) || 0;
  const cash = parseFloat(latest['Cash']) || 0;
  const posValue = parseFloat(latest['Positions Value']) || 0;
  const totalPnl = parseFloat(latest['Total PnL $']) || 0;
  const totalPnlPct = parseFloat(latest['Total PnL %']) || 0;
  const winRate = parseFloat(latest['Win Rate %']) || 0;
  const numOpen = parseInt(latest['Open Positions']) || openPositions.length;
  const numClosed = parseInt(latest['Closed Positions']) || closedPositions.length;

  // KPI cards
  $('kpiTotalValue').textContent = fmtMoney(totalValue);
  const pnlEl = $('kpiPnl');
  pnlEl.textContent = `${fmtMoney(totalPnl)} (${fmtPct(totalPnlPct)})`;
  pnlEl.className = 'kpi-card__delta ' + pnlClass(totalPnl);

  $('kpiOpenPositions').textContent = numOpen;
  $('kpiPositionsValue').textContent = fmtMoney(posValue) + ' invested';

  $('kpiSignalsToday').textContent = numOpen + numClosed;
  $('kpiTotalSignals').textContent = (numOpen + numClosed) + ' total trades';

  $('kpiWinRate').textContent = numClosed > 0 ? fmt(winRate, 1) + '%' : '—';
  $('kpiClosedTrades').textContent = numClosed + ' closed trades';

  // Performance summary
  $('perfClosed').textContent = numClosed;
  $('perfWinRate').textContent = numClosed > 0 ? fmt(winRate, 1) + '%' : '—';

  // Compute from closed positions
  const wins = closedPositions.filter(p => parseFloat(p['Realized PnL $']) > 0);
  const losses = closedPositions.filter(p => parseFloat(p['Realized PnL $']) <= 0);
  const avgWin = wins.length > 0 ? wins.reduce((s, p) => s + parseFloat(p['Realized PnL $']), 0) / wins.length : 0;
  const avgLoss = losses.length > 0 ? Math.abs(losses.reduce((s, p) => s + parseFloat(p['Realized PnL $']), 0) / losses.length) : 0;

  const avgWinEl = $('perfAvgWin');
  avgWinEl.textContent = fmtMoney(avgWin);
  avgWinEl.className = 'perf-stat__value mono ' + (avgWin > 0 ? 'positive' : 'neutral');

  const avgLossEl = $('perfAvgLoss');
  avgLossEl.textContent = fmtMoney(avgLoss);
  avgLossEl.className = 'perf-stat__value mono ' + (avgLoss > 0 ? 'negative' : 'neutral');

  const pf = avgLoss > 0 ? (avgWin / avgLoss) : 0;
  $('perfProfitFactor').textContent = pf > 0 ? fmt(pf, 2) : '—';

  const totalPnlEl = $('perfTotalPnl');
  totalPnlEl.textContent = fmtMoney(totalPnl);
  totalPnlEl.className = 'perf-stat__value mono ' + pnlClass(totalPnl);

  // Exit rules
  renderExitRules(closedPositions);

  // Open positions
  renderPositions(openPositions);

  // Unrealized PnL badge
  const totalUnrealized = openPositions.reduce((s, p) => s + (parseFloat(p['Unrealized PnL $']) || 0), 0);
  const unrealizedEl = $('unrealizedPnl');
  unrealizedEl.textContent = fmtMoney(totalUnrealized);
  unrealizedEl.className = 'panel__badge mono ' + pnlClass(totalUnrealized);

  // Portfolio allocation
  renderAllocation(cash, posValue, totalValue);
}

function renderPositions(positions) {
  const tbody = $('positionsBody');
  if (!positions || positions.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9" class="empty-state">No open positions</td></tr>';
    return;
  }

  tbody.innerHTML = positions.map(p => {
    const entry = parseFloat(p['Entry Price']) || 0;
    const current = parseFloat(p['Current Price']) || entry;
    const pnl = parseFloat(p['Unrealized PnL $']) || 0;
    const pnlPct = parseFloat(p['Unrealized PnL %']) || 0;
    const stop = parseFloat(p['Stop Price']) || 0;
    const target = parseFloat(p['Target Price']) || 0;
    const daysHeld = p['Opened At'] ? daysBetween(p['Opened At'], new Date().toISOString()) : 0;

    return `<tr>
      <td><strong>${p['Ticker'] || '—'}</strong></td>
      <td>${directionBadge(p['Direction'])}</td>
      <td>${fmtMoney(entry)}</td>
      <td>${fmtMoney(current)}</td>
      <td class="${pnlClass(pnl)}">${fmtMoney(pnl)}</td>
      <td class="${pnlClass(pnlPct)}">${fmtPct(pnlPct)}</td>
      <td style="color:var(--coral)">${fmtMoney(stop)}</td>
      <td style="color:var(--teal)">${fmtMoney(target)}</td>
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

  // Show most recent first (reverse)
  const recent = signals.slice().reverse().slice(0, 20);
  tbody.innerHTML = recent.map(s => {
    const time = shortDate(s['Generated At'] || '');
    const score = parseFloat(s['Score']) || 0;
    return `<tr>
      <td>${time}</td>
      <td><strong>${s['Ticker'] || '—'}</strong></td>
      <td>${directionBadge(s['Direction'])}</td>
      <td>${scoreBar(score)}</td>
      <td>${s['Confidence'] || '—'}</td>
      <td>${classificationBadge(s['Classification'])}</td>
      <td>${s['Status'] || '—'}</td>
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

  // Show most recent first
  const recent = filings.slice().reverse().slice(0, 50);
  feed.innerHTML = recent.map(f => {
    const time = shortDate(f['Detected At'] || f['Tx Date'] || '');
    const action = txnAction(f['Tx Code'] || '');
    const value = f['Dollar Value'] ? fmtMoney(parseFloat(f['Dollar Value']), 0) : '—';

    return `<div class="filing-item">
      <span class="filing-item__time">${time}</span>
      <span class="filing-item__info">
        <span class="filing-item__ticker">${f['Ticker'] || '—'}</span>
        <span class="filing-item__name">${f['Insider Name'] || '—'}</span>
        <span class="filing-item__action ${action.cls}">${action.label}</span>
      </span>
      <span class="filing-item__value">${value}</span>
    </div>`;
  }).join('');
}

function renderExitRules(closedPositions) {
  const tbody = $('exitRulesBody');

  if (!closedPositions || closedPositions.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3" class="empty-state">No closed trades yet</td></tr>';
    return;
  }

  // Group by exit rule
  const byRule = {};
  closedPositions.forEach(p => {
    const rule = p['Exit Rule'] || 'unknown';
    if (!byRule[rule]) byRule[rule] = { count: 0, pnl: 0 };
    byRule[rule].count++;
    byRule[rule].pnl += parseFloat(p['Realized PnL $']) || 0;
  });

  tbody.innerHTML = Object.entries(byRule).map(([rule, data]) => {
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
  const [filings, signals, openPositions, closedPositions, portfolioSnapshots, systemLogs] = await Promise.all([
    fetchSheet(SHEET_NAMES.filings),
    fetchSheet(SHEET_NAMES.signals),
    fetchSheet(SHEET_NAMES.openPositions),
    fetchSheet(SHEET_NAMES.closedPositions),
    fetchSheet(SHEET_NAMES.portfolio),
    fetchSheet(SHEET_NAMES.system),
  ]);

  renderState(systemLogs, portfolioSnapshots);
  renderSummary(portfolioSnapshots, closedPositions, openPositions);
  renderSignals(signals);
  renderFilings(filings);

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
