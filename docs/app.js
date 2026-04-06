// === INSIDER TRADE TRACKER — Frontend Logic ===

// Detect if running locally (Express backend) or on GitHub Pages (Sheets-only)
const IS_LOCAL = location.hostname === 'localhost' || location.hostname === '127.0.0.1';
const API_BASE = IS_LOCAL ? '' : null; // null = use Sheets
const SPREADSHEET_ID = '10_2yzOFxMic_lBAJLHwLEkg_1N8lqoQBEpNSUMRfef4';

// --- State ---
let portfolioData = null;
let equityChart = null;
let exitReasonChart = null;
let refreshInterval = null;

// --- Helpers ---
function fmt$(val) {
  if (val === null || val === undefined || isNaN(val)) return '--';
  const sign = val >= 0 ? '' : '-';
  return sign + '$' + Math.abs(val).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPct(val) {
  if (val === null || val === undefined || isNaN(val)) return '--';
  const sign = val > 0 ? '+' : '';
  return sign + val.toFixed(2) + '%';
}

function fmtPnlClass(val) {
  if (val > 0) return 'positive';
  if (val < 0) return 'negative';
  return '';
}

function fmtKpiSubClass(val) {
  if (val > 0) return 'positive';
  if (val < 0) return 'negative';
  return 'neutral';
}

function daysFromNow(dateStr) {
  if (!dateStr) return '--';
  const d = new Date(dateStr);
  const now = new Date();
  return Math.floor((now - d) / (1000 * 60 * 60 * 24));
}

function daysUntil(dateStr) {
  if (!dateStr) return '--';
  const d = new Date(dateStr);
  const now = new Date();
  const diff = Math.floor((d - now) / (1000 * 60 * 60 * 24));
  return diff;
}

function shortDate(dateStr) {
  if (!dateStr) return '--';
  const parts = dateStr.split('-');
  if (parts.length === 3) return parts[1] + '/' + parts[2];
  return dateStr;
}

// --- Toast ---
function showToast(message, type = 'success') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  
  setTimeout(() => {
    toast.classList.add('removing');
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// --- Panel Toggle ---
function togglePanel(bodyId, toggleId) {
  const body = document.getElementById(bodyId);
  const toggle = document.getElementById(toggleId);
  body.classList.toggle('collapsed');
  toggle.classList.toggle('collapsed');
}

// --- Confirmation Dialog ---
function showConfirm(title, message) {
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.className = 'dialog-overlay';
    overlay.innerHTML = `
      <div class="dialog-box">
        <h3>${title}</h3>
        <p>${message}</p>
        <div class="dialog-actions">
          <button class="btn-sm btn-cancel" id="dlgCancel">Cancel</button>
          <button class="btn-sm btn-confirm" id="dlgConfirm">Confirm</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    
    overlay.querySelector('#dlgCancel').onclick = () => { overlay.remove(); resolve(false); };
    overlay.querySelector('#dlgConfirm').onclick = () => { overlay.remove(); resolve(true); };
    overlay.onclick = (e) => { if (e.target === overlay) { overlay.remove(); resolve(false); } };
  });
}

// --- API calls ---
async function apiGet(path) {
  if (!IS_LOCAL) throw new Error('No backend');
  const res = await fetch(API_BASE + path);
  return res.json();
}

async function apiPost(path, body) {
  if (!IS_LOCAL) { showToast('Trade entry requires running locally', 'error'); return { error: 'Read-only' }; }
  const res = await fetch(API_BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return res.json();
}

// --- Google Sheets reader (for GitHub Pages) ---
async function fetchSheet(sheetName) {
  const url = `https://docs.google.com/spreadsheets/d/${SPREADSHEET_ID}/gviz/tq?tqx=out:json&sheet=${encodeURIComponent(sheetName)}`;
  try {
    const res = await fetch(url);
    const text = await res.text();
    const match = text.match(/google\.visualization\.Query\.setResponse\(([\s\S]+)\);?/);
    if (!match) return [];
    const data = JSON.parse(match[1]);
    const cols = data.table.cols.map(c => c.label || '');
    return (data.table.rows || []).map(r => {
      const obj = {};
      r.c.forEach((cell, i) => {
        if (cols[i]) obj[cols[i]] = cell ? (cell.v != null ? cell.v : (cell.f || '')) : '';
      });
      return obj;
    });
  } catch (e) {
    console.error(`Failed to fetch sheet "${sheetName}":`, e);
    return [];
  }
}

async function loadPortfolioFromSheets() {
  const [positions, closedTrades, history, settingsRows] = await Promise.all([
    fetchSheet('Open Positions'),
    fetchSheet('Closed Trades'),
    fetchSheet('Portfolio History'),
    fetchSheet('Settings'),
  ]);

  // Parse settings
  const settings = {};
  settingsRows.forEach(r => { if (r.Key) settings[r.Key] = r.Value; });
  const startingCapital = parseFloat(settings.starting_capital) || 100000;

  // Parse positions
  const parsedPositions = positions.map(p => ({
    tradeId: p['Trade ID'] || '',
    ticker: p['Ticker'] || '',
    company: p['Company'] || '',
    direction: p['Direction'] || 'LONG',
    entryDate: p['Entry Date'] || '',
    entryPrice: parseFloat(p['Entry Price']) || 0,
    shares: parseInt(p['Shares']) || 0,
    costBasis: parseFloat(p['Cost Basis']) || 0,
    currentPrice: parseFloat(p['Current Price']) || parseFloat(p['Entry Price']) || 0,
    unrealizedPnl: parseFloat(p['Unrealized PnL']) || 0,
    unrealizedPct: parseFloat(p['Unrealized %']) || 0,
    stopLoss: parseFloat(p['Stop Loss']) || 0,
    takeProfit: parseFloat(p['Take Profit']) || 0,
    trailingStopPct: parseFloat(p['Trailing Stop %']) || 0,
    expirationDate: p['Expiration Date'] || '',
    thesis: p['Thesis'] || '',
    source: p['Source'] || '',
    insiderName: p['Insider Name'] || '',
    insiderRole: p['Insider Role'] || '',
    filingUrl: p['Filing URL'] || '',
  }));

  // Parse closed trades
  const parsedClosed = closedTrades.map(t => ({
    tradeId: t['Trade ID'] || '',
    ticker: t['Ticker'] || '',
    company: t['Company'] || '',
    direction: t['Direction'] || 'LONG',
    entryDate: t['Entry Date'] || '',
    entryPrice: parseFloat(t['Entry Price']) || 0,
    exitDate: t['Exit Date'] || '',
    exitPrice: parseFloat(t['Exit Price']) || 0,
    shares: parseInt(t['Shares']) || 0,
    realizedPnl: parseFloat(t['Realized PnL']) || 0,
    realizedPct: parseFloat(t['Realized %']) || 0,
    exitReason: t['Exit Reason'] || '',
    daysHeld: parseInt(t['Days Held']) || 0,
  }));

  // Parse history
  const parsedHistory = history.map(h => ({
    date: h['Date'] || '',
    cash: parseFloat(h['Cash']) || 0,
    positionsValue: parseFloat(h['Positions Value']) || 0,
    totalValue: parseFloat(h['Total Value']) || 0,
    totalPnl: parseFloat(h['Total PnL']) || 0,
    totalPnlPct: parseFloat(h['Total PnL %']) || 0,
  }));

  // Calculate portfolio values
  const positionsValue = parsedPositions.reduce((s, p) => s + (p.currentPrice * p.shares), 0);
  const latestHist = parsedHistory.length > 0 ? parsedHistory[parsedHistory.length - 1] : null;
  const cash = latestHist ? latestHist.cash : startingCapital;
  const totalValue = cash + positionsValue;
  const totalPnl = totalValue - startingCapital;
  const totalPnlPct = (totalPnl / startingCapital) * 100;

  // Performance
  const wins = parsedClosed.filter(t => t.realizedPnl > 0);
  const losses = parsedClosed.filter(t => t.realizedPnl <= 0);
  const winRate = parsedClosed.length > 0 ? (wins.length / parsedClosed.length) * 100 : 0;
  const avgWin = wins.length > 0 ? wins.reduce((s, t) => s + t.realizedPnl, 0) / wins.length : 0;
  const avgLoss = losses.length > 0 ? Math.abs(losses.reduce((s, t) => s + t.realizedPnl, 0) / losses.length) : 0;
  const profitFactor = avgLoss > 0 ? avgWin / avgLoss : avgWin > 0 ? Infinity : 0;
  const avgDaysHeld = parsedClosed.length > 0 ? parsedClosed.reduce((s, t) => s + t.daysHeld, 0) / parsedClosed.length : 0;
  const bestTrade = parsedClosed.length > 0 ? parsedClosed.reduce((b, t) => t.realizedPnl > b.realizedPnl ? t : b, parsedClosed[0]) : null;
  const worstTrade = parsedClosed.length > 0 ? parsedClosed.reduce((w, t) => t.realizedPnl < w.realizedPnl ? t : w, parsedClosed[0]) : null;

  return {
    cash, positionsValue, totalValue, totalPnl, totalPnlPct, startingCapital,
    positions: parsedPositions,
    closedTrades: parsedClosed,
    settings,
    history: parsedHistory,
    performance: { totalTrades: parsedClosed.length, wins: wins.length, losses: losses.length, winRate, avgWin, avgLoss, profitFactor, avgDaysHeld, bestTrade, worstTrade },
  };
}

// --- Load Portfolio ---
async function loadPortfolio() {
  try {
    if (IS_LOCAL) {
      portfolioData = await apiGet('/api/portfolio');
    } else {
      portfolioData = await loadPortfolioFromSheets();
    }
    renderDashboard();
  } catch (err) {
    console.error('Failed to load portfolio:', err);
    showToast('Failed to load data: ' + err.message, 'error');
  }
}

// --- Render ---
function renderDashboard() {
  const d = portfolioData;
  if (!d) return;
  
  // Day counter
  const expStart = d.settings.experiment_start || '2026-04-06';
  const expEnd = d.settings.experiment_end || '2026-07-06';
  const startDate = new Date(expStart);
  const dayNum = Math.max(1, Math.floor((new Date() - startDate) / (1000 * 60 * 60 * 24)) + 1);
  document.getElementById('dayCounter').innerHTML = `Day <span>${Math.min(dayNum, 90)}</span>/90`;
  document.getElementById('experimentDates').textContent = `Experiment: ${expStart} to ${expEnd}`;
  
  // Top bar value
  document.getElementById('topPortfolioValue').textContent = fmt$(d.totalValue);
  
  // KPI cards
  document.getElementById('kpiTotalValue').textContent = fmt$(d.totalValue);
  const pnlStr = `${d.totalPnl >= 0 ? '+' : ''}${fmt$(d.totalPnl)} (${fmtPct(d.totalPnlPct)})`;
  const kpiPnlEl = document.getElementById('kpiTotalPnl');
  kpiPnlEl.textContent = pnlStr;
  kpiPnlEl.className = 'kpi-sub font-mono ' + fmtKpiSubClass(d.totalPnl);
  
  document.getElementById('kpiCash').textContent = fmt$(d.cash);
  const cashPct = d.totalValue > 0 ? ((d.cash / d.totalValue) * 100).toFixed(1) : '100.0';
  document.getElementById('kpiCashPct').textContent = cashPct + '% of portfolio';
  
  document.getElementById('kpiOpenCount').textContent = d.positions.length;
  document.getElementById('kpiInvested').textContent = fmt$(d.positionsValue) + ' invested';
  
  const wr = d.performance.totalTrades > 0 ? d.performance.winRate.toFixed(1) + '%' : '--%';
  document.getElementById('kpiWinRate').textContent = wr;
  document.getElementById('kpiClosedCount').textContent = d.closedTrades.length + ' closed trades';
  
  // Open positions badge
  document.getElementById('openPosBadge').textContent = d.positions.length;
  
  // Closed badge
  document.getElementById('closedBadge').textContent = d.closedTrades.length;
  
  // Open positions table
  renderOpenPositions(d.positions);
  
  // Closed trades table
  renderClosedTrades(d.closedTrades);
  
  // Performance stats
  renderPerformanceStats(d.performance, d.totalPnl, d.totalPnlPct);
  
  // Charts
  renderEquityChart(d.history, d.startingCapital);
  renderExitReasonChart(d.closedTrades);
  
  // Set default expiration date on form
  const defaultExpDays = parseInt(d.settings.default_expiration_days) || 60;
  const expInput = document.getElementById('expirationDate');
  if (!expInput.value) {
    const expDate = new Date();
    expDate.setDate(expDate.getDate() + defaultExpDays);
    expInput.value = expDate.toISOString().split('T')[0];
  }
}

function renderOpenPositions(positions) {
  const tbody = document.getElementById('openPosTableBody');
  
  if (positions.length === 0) {
    tbody.innerHTML = '<tr><td colspan="11" class="empty-state"><div class="empty-icon">📭</div>No open positions</td></tr>';
    return;
  }
  
  tbody.innerHTML = positions.map((p, idx) => {
    const days = daysFromNow(p.entryDate);
    const expDays = daysUntil(p.expirationDate);
    const expWarning = expDays !== '--' && expDays <= 5 ? ' style="color: var(--amber)"' : '';
    
    return `
      <tr id="pos-row-${p.tradeId}">
        <td><strong>${p.ticker}</strong></td>
        <td>${p.direction === 'LONG' ? '▲ L' : '▼ S'}</td>
        <td>${fmt$(p.entryPrice)}</td>
        <td>${fmt$(p.currentPrice)}</td>
        <td class="${fmtPnlClass(p.unrealizedPnl)}">${p.unrealizedPnl >= 0 ? '+' : ''}${fmt$(p.unrealizedPnl)}</td>
        <td class="${fmtPnlClass(p.unrealizedPct)}">${fmtPct(p.unrealizedPct)}</td>
        <td>${fmt$(p.stopLoss)}</td>
        <td>${fmt$(p.takeProfit)}</td>
        <td${expWarning}>${shortDate(p.expirationDate)}</td>
        <td>${days}d</td>
        <td>
          ${IS_LOCAL ? `<div class="action-btns">
            <button class="btn-sm btn-close" onclick="showCloseForm('${p.tradeId}')">Close</button>
            <button class="btn-sm btn-edit" onclick="showEditForm('${p.tradeId}', ${p.stopLoss}, ${p.takeProfit}, ${p.trailingStopPct || 0}, '${p.expirationDate}')">Edit</button>
          </div>` : ''}
        </td>
      </tr>
      <tr id="close-form-${p.tradeId}" style="display:none;">
        <td colspan="11" style="padding:0;">
          <div class="inline-form active">
            <div class="form-group">
              <label>Exit Price</label>
              <input type="number" step="0.01" id="closePrice-${p.tradeId}" placeholder="0.00">
            </div>
            <div class="form-group">
              <label>Exit Reason</label>
              <select id="closeReason-${p.tradeId}">
                <option value="target hit">Target Hit</option>
                <option value="stop hit">Stop Hit</option>
                <option value="expiration">Expiration</option>
                <option value="manual" selected>Manual</option>
                <option value="thesis invalidated">Thesis Invalidated</option>
              </select>
            </div>
            <div class="form-group" style="align-self: flex-end;">
              <button class="btn-sm btn-confirm" onclick="handleCloseTrade('${p.tradeId}')">Confirm Close</button>
            </div>
            <div class="form-group" style="align-self: flex-end;">
              <button class="btn-sm btn-cancel" onclick="hideCloseForm('${p.tradeId}')">Cancel</button>
            </div>
          </div>
        </td>
      </tr>
      <tr id="edit-form-${p.tradeId}" style="display:none;">
        <td colspan="11" style="padding:0;">
          <div class="inline-form active">
            <div class="form-group">
              <label>Stop Loss</label>
              <input type="number" step="0.01" id="editSL-${p.tradeId}" value="${p.stopLoss || ''}">
            </div>
            <div class="form-group">
              <label>Take Profit</label>
              <input type="number" step="0.01" id="editTP-${p.tradeId}" value="${p.takeProfit || ''}">
            </div>
            <div class="form-group">
              <label>Trail %</label>
              <input type="number" step="0.1" id="editTrail-${p.tradeId}" value="${p.trailingStopPct || ''}" style="width:80px;">
            </div>
            <div class="form-group">
              <label>Expiration</label>
              <input type="date" id="editExp-${p.tradeId}" value="${p.expirationDate || ''}" style="width:140px;">
            </div>
            <div class="form-group" style="align-self: flex-end;">
              <button class="btn-sm btn-confirm" onclick="handleEditTrade('${p.tradeId}')">Save</button>
            </div>
            <div class="form-group" style="align-self: flex-end;">
              <button class="btn-sm btn-cancel" onclick="hideEditForm('${p.tradeId}')">Cancel</button>
            </div>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

function renderClosedTrades(trades) {
  const tbody = document.getElementById('closedTableBody');
  
  if (trades.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9" class="empty-state"><div class="empty-icon">📋</div>No closed trades yet</td></tr>';
    return;
  }
  
  // Sort by exit date descending
  const sorted = [...trades].sort((a, b) => (b.exitDate || '').localeCompare(a.exitDate || ''));
  
  tbody.innerHTML = sorted.map(t => `
    <tr>
      <td><strong>${t.ticker}</strong></td>
      <td>${t.direction === 'LONG' ? '▲ L' : '▼ S'}</td>
      <td>${fmt$(t.entryPrice)}</td>
      <td>${fmt$(t.exitPrice)}</td>
      <td class="${fmtPnlClass(t.realizedPnl)}">${t.realizedPnl >= 0 ? '+' : ''}${fmt$(t.realizedPnl)}</td>
      <td class="${fmtPnlClass(t.realizedPct)}">${fmtPct(t.realizedPct)}</td>
      <td>${t.exitReason}</td>
      <td>${t.daysHeld}d</td>
      <td>${shortDate(t.exitDate)}</td>
    </tr>
  `).join('');
}

function renderPerformanceStats(perf, totalPnl, totalPnlPct) {
  document.getElementById('statTotalPnl').textContent = fmt$(totalPnl);
  document.getElementById('statTotalPnl').style.color = totalPnl >= 0 ? 'var(--teal)' : 'var(--coral)';
  
  document.getElementById('statTotalReturn').textContent = fmtPct(totalPnlPct);
  document.getElementById('statTotalReturn').style.color = totalPnlPct >= 0 ? 'var(--teal)' : 'var(--coral)';
  
  document.getElementById('statWinRate').textContent = perf.totalTrades > 0 ? perf.winRate.toFixed(1) + '%' : '--';
  
  const pf = perf.profitFactor;
  document.getElementById('statProfitFactor').textContent = pf === Infinity ? '∞' : pf > 0 ? pf.toFixed(2) : '--';
  
  document.getElementById('statAvgWin').textContent = perf.wins > 0 ? fmt$(perf.avgWin) : '--';
  if (perf.wins > 0) document.getElementById('statAvgWin').style.color = 'var(--teal)';
  
  document.getElementById('statAvgLoss').textContent = perf.losses > 0 ? '-' + fmt$(perf.avgLoss) : '--';
  if (perf.losses > 0) document.getElementById('statAvgLoss').style.color = 'var(--coral)';
  
  if (perf.bestTrade) {
    document.getElementById('statBestTrade').textContent = `${perf.bestTrade.ticker} ${fmt$(perf.bestTrade.realizedPnl)}`;
    document.getElementById('statBestTrade').style.color = 'var(--teal)';
  } else {
    document.getElementById('statBestTrade').textContent = '--';
  }
  
  if (perf.worstTrade) {
    document.getElementById('statWorstTrade').textContent = `${perf.worstTrade.ticker} ${fmt$(perf.worstTrade.realizedPnl)}`;
    document.getElementById('statWorstTrade').style.color = 'var(--coral)';
  } else {
    document.getElementById('statWorstTrade').textContent = '--';
  }
  
  document.getElementById('statAvgDays').textContent = perf.totalTrades > 0 ? perf.avgDaysHeld.toFixed(1) + 'd' : '--';
  document.getElementById('statTotalTrades').textContent = perf.totalTrades;
}

// --- Charts ---
function renderEquityChart(history, startingCapital) {
  const ctx = document.getElementById('equityChart').getContext('2d');
  
  const labels = history.length > 0 ? history.map(h => h.date) : ['Start'];
  const data = history.length > 0 ? history.map(h => h.totalValue) : [startingCapital];
  
  if (equityChart) {
    equityChart.data.labels = labels;
    equityChart.data.datasets[0].data = data;
    equityChart.data.datasets[1].data = labels.map(() => startingCapital);
    equityChart.update('none');
    return;
  }
  
  equityChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Portfolio Value',
          data,
          borderColor: '#00d4aa',
          backgroundColor: 'rgba(0, 212, 170, 0.08)',
          borderWidth: 2,
          fill: true,
          tension: 0.3,
          pointRadius: history.length > 20 ? 0 : 3,
          pointBackgroundColor: '#00d4aa',
        },
        {
          label: 'Starting Capital',
          data: labels.map(() => startingCapital),
          borderColor: 'rgba(255,255,255,0.15)',
          borderWidth: 1,
          borderDash: [6, 4],
          pointRadius: 0,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false,
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#1a1d27',
          borderColor: '#2a2d3a',
          borderWidth: 1,
          titleFont: { family: "'JetBrains Mono', monospace", size: 11 },
          bodyFont: { family: "'JetBrains Mono', monospace", size: 11 },
          callbacks: {
            label: (ctx) => ctx.dataset.label + ': ' + fmt$(ctx.parsed.y),
          },
        },
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: {
            font: { family: "'JetBrains Mono', monospace", size: 10 },
            color: '#6b7185',
            maxTicksLimit: 8,
          },
        },
        y: {
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: {
            font: { family: "'JetBrains Mono', monospace", size: 10 },
            color: '#6b7185',
            callback: (v) => '$' + (v / 1000).toFixed(0) + 'k',
          },
        },
      },
    },
  });
}

function renderExitReasonChart(closedTrades) {
  const ctx = document.getElementById('exitReasonChart').getContext('2d');
  
  // Count exit reasons
  const counts = {};
  for (const t of closedTrades) {
    const reason = t.exitReason || 'manual';
    counts[reason] = (counts[reason] || 0) + 1;
  }
  
  const labels = Object.keys(counts);
  const data = Object.values(counts);
  const colors = ['#00d4aa', '#ff6b6b', '#ffa726', '#5b9cf6', '#b18cfe', '#ff9cda'];
  
  if (exitReasonChart) {
    exitReasonChart.data.labels = labels;
    exitReasonChart.data.datasets[0].data = data;
    exitReasonChart.data.datasets[0].backgroundColor = colors.slice(0, labels.length);
    exitReasonChart.update('none');
    return;
  }
  
  exitReasonChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels.length > 0 ? labels : ['No data'],
      datasets: [{
        data: data.length > 0 ? data : [1],
        backgroundColor: data.length > 0 ? colors.slice(0, labels.length) : ['#2a2d3a'],
        borderColor: '#1a1d27',
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '65%',
      plugins: {
        legend: {
          position: 'right',
          labels: {
            font: { family: "'JetBrains Mono', monospace", size: 10 },
            color: '#9aa0b0',
            padding: 12,
            boxWidth: 12,
            boxHeight: 12,
          },
        },
        tooltip: {
          backgroundColor: '#1a1d27',
          borderColor: '#2a2d3a',
          borderWidth: 1,
          titleFont: { family: "'JetBrains Mono', monospace", size: 11 },
          bodyFont: { family: "'JetBrains Mono', monospace", size: 11 },
        },
      },
    },
  });
}

// --- Trade Actions ---
function showCloseForm(tradeId) {
  // Hide any other open forms
  document.querySelectorAll('[id^="close-form-"]').forEach(el => el.style.display = 'none');
  document.querySelectorAll('[id^="edit-form-"]').forEach(el => el.style.display = 'none');
  document.getElementById(`close-form-${tradeId}`).style.display = '';
}

function hideCloseForm(tradeId) {
  document.getElementById(`close-form-${tradeId}`).style.display = 'none';
}

function showEditForm(tradeId, sl, tp, trail, exp) {
  document.querySelectorAll('[id^="close-form-"]').forEach(el => el.style.display = 'none');
  document.querySelectorAll('[id^="edit-form-"]').forEach(el => el.style.display = 'none');
  document.getElementById(`edit-form-${tradeId}`).style.display = '';
}

function hideEditForm(tradeId) {
  document.getElementById(`edit-form-${tradeId}`).style.display = 'none';
}

async function handleCloseTrade(tradeId) {
  const exitPrice = parseFloat(document.getElementById(`closePrice-${tradeId}`).value);
  const exitReason = document.getElementById(`closeReason-${tradeId}`).value;
  
  if (!exitPrice || exitPrice <= 0) {
    showToast('Enter a valid exit price', 'error');
    return;
  }
  
  // Find the position to show ticker in confirmation
  const pos = portfolioData.positions.find(p => p.tradeId === tradeId);
  const ticker = pos ? pos.ticker : tradeId;
  
  const confirmed = await showConfirm(
    'Close Position',
    `Close ${ticker} at $${exitPrice.toFixed(2)}? Reason: ${exitReason}`
  );
  
  if (!confirmed) return;
  
  try {
    const result = await apiPost('/api/trade/close', { tradeId, exitPrice, exitReason });
    if (result.error) {
      showToast(result.error, 'error');
    } else {
      showToast(result.message, 'success');
      await loadPortfolio();
    }
  } catch (err) {
    showToast('Failed to close trade: ' + err.message, 'error');
  }
}

async function handleEditTrade(tradeId) {
  const stopLoss = parseFloat(document.getElementById(`editSL-${tradeId}`).value) || undefined;
  const takeProfit = parseFloat(document.getElementById(`editTP-${tradeId}`).value) || undefined;
  const trailingStopPct = parseFloat(document.getElementById(`editTrail-${tradeId}`).value) || undefined;
  const expirationDate = document.getElementById(`editExp-${tradeId}`).value || undefined;
  
  try {
    const result = await apiPost('/api/trade/edit', { tradeId, stopLoss, takeProfit, trailingStopPct, expirationDate });
    if (result.error) {
      showToast(result.error, 'error');
    } else {
      showToast(result.message, 'success');
      hideEditForm(tradeId);
      await loadPortfolio();
    }
  } catch (err) {
    showToast('Failed to edit trade: ' + err.message, 'error');
  }
}

// --- New Trade ---
async function handleNewTrade(event) {
  event.preventDefault();
  
  const btn = document.getElementById('submitTradeBtn');
  btn.disabled = true;
  btn.textContent = 'SUBMITTING...';
  
  const body = {
    ticker: document.getElementById('ticker').value.trim().toUpperCase(),
    direction: document.getElementById('direction').value,
    entryPrice: parseFloat(document.getElementById('entryPrice').value),
    shares: parseInt(document.getElementById('shares').value),
    stopLoss: parseFloat(document.getElementById('stopLoss').value) || undefined,
    takeProfit: parseFloat(document.getElementById('takeProfit').value) || undefined,
    trailingStopPct: parseFloat(document.getElementById('trailingStopPct').value) || undefined,
    expirationDate: document.getElementById('expirationDate').value || undefined,
    company: document.getElementById('company').value.trim(),
    source: document.getElementById('source').value,
    insiderName: document.getElementById('insiderName').value.trim(),
    insiderRole: document.getElementById('insiderRole').value.trim(),
    filingUrl: document.getElementById('filingUrl').value.trim(),
    thesis: document.getElementById('thesis').value.trim(),
  };
  
  // Validation
  if (!body.ticker) {
    showToast('Ticker is required', 'error');
    btn.disabled = false;
    btn.textContent = '⚡ ENTER TRADE';
    return;
  }
  if (!body.entryPrice || body.entryPrice <= 0) {
    showToast('Entry price must be > 0', 'error');
    btn.disabled = false;
    btn.textContent = '⚡ ENTER TRADE';
    return;
  }
  if (!body.shares || body.shares <= 0) {
    showToast('Shares must be > 0', 'error');
    btn.disabled = false;
    btn.textContent = '⚡ ENTER TRADE';
    return;
  }
  
  try {
    const result = await apiPost('/api/trade/open', body);
    if (result.error) {
      showToast(result.error, 'error');
    } else {
      showToast(result.message, 'success');
      // Reset form
      document.getElementById('newTradeForm').reset();
      // Reset default expiration
      if (portfolioData && portfolioData.settings) {
        const defaultExpDays = parseInt(portfolioData.settings.default_expiration_days) || 60;
        const expDate = new Date();
        expDate.setDate(expDate.getDate() + defaultExpDays);
        document.getElementById('expirationDate').value = expDate.toISOString().split('T')[0];
      }
      await loadPortfolio();
    }
  } catch (err) {
    showToast('Failed to open trade: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '⚡ ENTER TRADE';
  }
}

// --- Init ---
document.addEventListener('DOMContentLoaded', () => {
  // Hide trade entry form and action buttons on GitHub Pages (read-only)
  if (!IS_LOCAL) {
    const tradeForm = document.querySelector('.panel-collapsible');
    if (tradeForm) tradeForm.style.display = 'none';
  }

  loadPortfolio();
  // Auto-refresh every 60 seconds
  refreshInterval = setInterval(loadPortfolio, 60000);
});
