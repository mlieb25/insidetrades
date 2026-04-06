const express = require('express');
const path = require('path');
const { google } = require('googleapis');
const crypto = require('crypto');

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// --- Google Sheets Setup ---
const SPREADSHEET_ID = '10_2yzOFxMic_lBAJLHwLEkg_1N8lqoQBEpNSUMRfef4';
const CREDENTIALS_PATH = '/home/user/workspace/trade_monitor/credentials/service_account.json';

let sheets;
async function initSheets() {
  const auth = new google.auth.GoogleAuth({
    keyFile: CREDENTIALS_PATH,
    scopes: ['https://www.googleapis.com/auth/spreadsheets'],
  });
  const client = await auth.getClient();
  sheets = google.sheets({ version: 'v4', auth: client });
}

// --- Helper functions ---
async function getSheetData(range) {
  const res = await sheets.spreadsheets.values.get({
    spreadsheetId: SPREADSHEET_ID,
    range,
  });
  return res.data.values || [];
}

async function appendRow(range, values) {
  await sheets.spreadsheets.values.append({
    spreadsheetId: SPREADSHEET_ID,
    range,
    valueInputOption: 'USER_ENTERED',
    insertDataOption: 'INSERT_ROWS',
    requestBody: { values: [values] },
  });
}

async function updateRow(range, values) {
  await sheets.spreadsheets.values.update({
    spreadsheetId: SPREADSHEET_ID,
    range,
    valueInputOption: 'USER_ENTERED',
    requestBody: { values: [values] },
  });
}

async function deleteRow(sheetName, rowIndex) {
  // Get sheet ID from name
  const meta = await sheets.spreadsheets.get({ spreadsheetId: SPREADSHEET_ID });
  const sheet = meta.data.sheets.find(s => s.properties.title === sheetName);
  if (!sheet) throw new Error(`Sheet "${sheetName}" not found`);
  
  await sheets.spreadsheets.batchUpdate({
    spreadsheetId: SPREADSHEET_ID,
    requestBody: {
      requests: [{
        deleteDimension: {
          range: {
            sheetId: sheet.properties.sheetId,
            dimension: 'ROWS',
            startIndex: rowIndex,
            endIndex: rowIndex + 1,
          },
        },
      }],
    },
  });
}

function generateTradeId() {
  return 'T-' + crypto.randomBytes(3).toString('hex').toUpperCase();
}

function formatDate(date) {
  return date.toISOString().split('T')[0];
}

function formatTimestamp() {
  return new Date().toISOString().replace('T', ' ').split('.')[0];
}

// --- Settings ---
async function getSettings() {
  const rows = await getSheetData('Settings!A2:B');
  const settings = {};
  for (const row of rows) {
    if (row[0]) settings[row[0]] = row[1];
  }
  return settings;
}

// --- Portfolio calculations ---
async function getLatestPortfolioHistory() {
  const rows = await getSheetData('Portfolio History!A2:I');
  if (rows.length === 0) return null;
  const last = rows[rows.length - 1];
  return {
    date: last[0],
    cash: parseFloat(last[1]) || 0,
    positionsValue: parseFloat(last[2]) || 0,
    totalValue: parseFloat(last[3]) || 0,
    totalPnl: parseFloat(last[4]) || 0,
    totalPnlPct: parseFloat(last[5]) || 0,
    openCount: parseInt(last[6]) || 0,
    closedCount: parseInt(last[7]) || 0,
    winRate: parseFloat(last[8]) || 0,
  };
}

async function calculateAndUpdatePortfolio() {
  const settings = await getSettings();
  const startingCapital = parseFloat(settings.starting_capital) || 100000;
  
  const openRows = await getSheetData('Open Positions!A2:T');
  const closedRows = await getSheetData('Closed Trades!A2:T');
  
  // Calculate positions value
  let positionsValue = 0;
  for (const row of openRows) {
    const costBasis = parseFloat(row[7]) || 0;
    positionsValue += costBasis;
  }
  
  // Calculate realized PnL from closed trades
  let realizedPnl = 0;
  let wins = 0;
  for (const row of closedRows) {
    const pnl = parseFloat(row[9]) || 0;
    realizedPnl += pnl;
    if (pnl > 0) wins++;
  }
  
  // Cash = starting capital - invested + realized PnL
  const invested = positionsValue;
  const cash = startingCapital - invested + realizedPnl;
  const totalValue = cash + positionsValue;
  const totalPnl = totalValue - startingCapital;
  const totalPnlPct = ((totalPnl / startingCapital) * 100);
  const winRate = closedRows.length > 0 ? ((wins / closedRows.length) * 100) : 0;
  
  // Append to portfolio history
  await appendRow('Portfolio History!A:I', [
    formatDate(new Date()),
    cash.toFixed(2),
    positionsValue.toFixed(2),
    totalValue.toFixed(2),
    totalPnl.toFixed(2),
    totalPnlPct.toFixed(2),
    openRows.length,
    closedRows.length,
    winRate.toFixed(1),
  ]);
  
  return { cash, positionsValue, totalValue, totalPnl, totalPnlPct, winRate };
}

// --- API Routes ---

// GET /api/settings
app.get('/api/settings', async (req, res) => {
  try {
    const settings = await getSettings();
    res.json(settings);
  } catch (err) {
    console.error('GET /api/settings error:', err.message);
    res.status(400).json({ error: err.message });
  }
});

// GET /api/portfolio
app.get('/api/portfolio', async (req, res) => {
  try {
    const settings = await getSettings();
    const startingCapital = parseFloat(settings.starting_capital) || 100000;
    
    // Open positions
    const openRows = await getSheetData('Open Positions!A2:T');
    const positions = openRows.map(row => ({
      tradeId: row[0] || '',
      ticker: row[1] || '',
      company: row[2] || '',
      direction: row[3] || '',
      entryDate: row[4] || '',
      entryPrice: parseFloat(row[5]) || 0,
      shares: parseInt(row[6]) || 0,
      costBasis: parseFloat(row[7]) || 0,
      currentPrice: parseFloat(row[8]) || 0,
      unrealizedPnl: parseFloat(row[9]) || 0,
      unrealizedPct: parseFloat(row[10]) || 0,
      stopLoss: parseFloat(row[11]) || 0,
      takeProfit: parseFloat(row[12]) || 0,
      trailingStopPct: parseFloat(row[13]) || 0,
      expirationDate: row[14] || '',
      thesis: row[15] || '',
      source: row[16] || '',
      insiderName: row[17] || '',
      insiderRole: row[18] || '',
      filingUrl: row[19] || '',
    }));
    
    // Closed trades
    const closedRows = await getSheetData('Closed Trades!A2:T');
    const closedTrades = closedRows.map(row => ({
      tradeId: row[0] || '',
      ticker: row[1] || '',
      company: row[2] || '',
      direction: row[3] || '',
      entryDate: row[4] || '',
      entryPrice: parseFloat(row[5]) || 0,
      exitDate: row[6] || '',
      exitPrice: parseFloat(row[7]) || 0,
      shares: parseInt(row[8]) || 0,
      realizedPnl: parseFloat(row[9]) || 0,
      realizedPct: parseFloat(row[10]) || 0,
      exitReason: row[11] || '',
      daysHeld: parseInt(row[12]) || 0,
      stopLoss: parseFloat(row[13]) || 0,
      takeProfit: parseFloat(row[14]) || 0,
      thesis: row[15] || '',
      source: row[16] || '',
      insiderName: row[17] || '',
      insiderRole: row[18] || '',
      filingUrl: row[19] || '',
    }));
    
    // Portfolio history
    const historyRows = await getSheetData('Portfolio History!A2:I');
    const history = historyRows.map(row => ({
      date: row[0] || '',
      cash: parseFloat(row[1]) || 0,
      positionsValue: parseFloat(row[2]) || 0,
      totalValue: parseFloat(row[3]) || 0,
      totalPnl: parseFloat(row[4]) || 0,
      totalPnlPct: parseFloat(row[5]) || 0,
      openCount: parseInt(row[6]) || 0,
      closedCount: parseInt(row[7]) || 0,
      winRate: parseFloat(row[8]) || 0,
    }));
    
    // Calculate current state
    let positionsValue = 0;
    for (const p of positions) {
      positionsValue += p.costBasis;
    }
    
    let realizedPnl = 0;
    let wins = 0;
    let totalWinAmt = 0;
    let totalLossAmt = 0;
    let bestTrade = null;
    let worstTrade = null;
    let totalDaysHeld = 0;
    
    for (const t of closedTrades) {
      realizedPnl += t.realizedPnl;
      totalDaysHeld += t.daysHeld;
      if (t.realizedPnl > 0) {
        wins++;
        totalWinAmt += t.realizedPnl;
      } else {
        totalLossAmt += Math.abs(t.realizedPnl);
      }
      if (!bestTrade || t.realizedPnl > bestTrade.realizedPnl) bestTrade = t;
      if (!worstTrade || t.realizedPnl < worstTrade.realizedPnl) worstTrade = t;
    }
    
    const cash = startingCapital - positionsValue + realizedPnl;
    const totalValue = cash + positionsValue;
    const totalPnl = totalValue - startingCapital;
    const totalPnlPct = (totalPnl / startingCapital) * 100;
    const winRate = closedTrades.length > 0 ? (wins / closedTrades.length) * 100 : 0;
    const losses = closedTrades.length - wins;
    const avgWin = wins > 0 ? totalWinAmt / wins : 0;
    const avgLoss = losses > 0 ? totalLossAmt / losses : 0;
    const profitFactor = totalLossAmt > 0 ? totalWinAmt / totalLossAmt : totalWinAmt > 0 ? Infinity : 0;
    const avgDaysHeld = closedTrades.length > 0 ? totalDaysHeld / closedTrades.length : 0;
    
    res.json({
      cash,
      positionsValue,
      totalValue,
      totalPnl,
      totalPnlPct,
      startingCapital,
      positions,
      closedTrades,
      settings,
      history,
      performance: {
        winRate,
        avgWin,
        avgLoss,
        profitFactor,
        bestTrade,
        worstTrade,
        avgDaysHeld,
        totalTrades: closedTrades.length,
        wins,
        losses,
      },
    });
  } catch (err) {
    console.error('GET /api/portfolio error:', err.message);
    res.status(400).json({ error: err.message });
  }
});

// POST /api/trade/open
app.post('/api/trade/open', async (req, res) => {
  try {
    const {
      ticker, direction, entryPrice, shares,
      stopLoss, takeProfit, trailingStopPct,
      expirationDate, company, source,
      insiderName, insiderRole, filingUrl, thesis
    } = req.body;
    
    // Validation
    if (!ticker || !ticker.trim()) return res.status(400).json({ error: 'Ticker is required' });
    if (!entryPrice || entryPrice <= 0) return res.status(400).json({ error: 'Entry price must be > 0' });
    if (!shares || shares <= 0) return res.status(400).json({ error: 'Shares must be > 0' });
    
    const settings = await getSettings();
    const startingCapital = parseFloat(settings.starting_capital) || 100000;
    const defaultStopPct = parseFloat(settings.default_stop_pct) || 5;
    const defaultTargetPct = parseFloat(settings.default_target_pct) || 10;
    const defaultExpDays = parseInt(settings.default_expiration_days) || 60;
    const maxPositionPct = parseFloat(settings.max_position_pct) || 10;
    
    const costBasis = entryPrice * shares;
    
    // Get current portfolio state
    const openRows = await getSheetData('Open Positions!A2:T');
    const closedRows = await getSheetData('Closed Trades!A2:T');
    
    let positionsValue = 0;
    for (const row of openRows) {
      positionsValue += parseFloat(row[7]) || 0;
    }
    let realizedPnl = 0;
    for (const row of closedRows) {
      realizedPnl += parseFloat(row[9]) || 0;
    }
    
    const cash = startingCapital - positionsValue + realizedPnl;
    const totalValue = cash + positionsValue;
    
    // Check cash
    if (costBasis > cash) {
      return res.status(400).json({ error: `Insufficient cash. Need $${costBasis.toFixed(2)}, have $${cash.toFixed(2)}` });
    }
    
    // Check max position size
    const maxPosition = totalValue * (maxPositionPct / 100);
    if (costBasis > maxPosition) {
      return res.status(400).json({ error: `Position exceeds ${maxPositionPct}% max. Limit: $${maxPosition.toFixed(2)}` });
    }
    
    const tradeId = generateTradeId();
    const entryDate = formatDate(new Date());
    
    // Calculate defaults
    let sl = stopLoss;
    let tp = takeProfit;
    if (!sl || sl <= 0) {
      sl = direction === 'LONG'
        ? entryPrice * (1 - defaultStopPct / 100)
        : entryPrice * (1 + defaultStopPct / 100);
    }
    if (!tp || tp <= 0) {
      tp = direction === 'LONG'
        ? entryPrice * (1 + defaultTargetPct / 100)
        : entryPrice * (1 - defaultTargetPct / 100);
    }
    
    let expDate = expirationDate;
    if (!expDate) {
      const d = new Date();
      d.setDate(d.getDate() + defaultExpDays);
      expDate = formatDate(d);
    }
    
    const tickerUpper = ticker.trim().toUpperCase();
    
    // Write to Open Positions
    // Trade ID, Ticker, Company, Direction, Entry Date, Entry Price, Shares, Cost Basis, Current Price, Unrealized PnL, Unrealized %, Stop Loss, Take Profit, Trailing Stop %, Expiration Date, Thesis, Source, Insider Name, Insider Role, Filing URL
    await appendRow('Open Positions!A:T', [
      tradeId,
      tickerUpper,
      company || '',
      direction || 'LONG',
      entryDate,
      entryPrice,
      shares,
      costBasis.toFixed(2),
      entryPrice, // current = entry at open
      '0.00',     // unrealized PnL
      '0.00',     // unrealized %
      parseFloat(sl).toFixed(2),
      parseFloat(tp).toFixed(2),
      trailingStopPct || '',
      expDate,
      thesis || '',
      source || '',
      insiderName || '',
      insiderRole || '',
      filingUrl || '',
    ]);
    
    // Log to Trade Log
    await appendRow('Trade Log!A:E', [
      formatTimestamp(),
      tradeId,
      'OPEN',
      tickerUpper,
      `${direction} ${shares} shares @ $${entryPrice} | Cost: $${costBasis.toFixed(2)}`,
    ]);
    
    res.json({
      success: true,
      tradeId,
      message: `Opened ${direction} position: ${shares} ${tickerUpper} @ $${entryPrice}`,
    });
  } catch (err) {
    console.error('POST /api/trade/open error:', err.message);
    res.status(400).json({ error: err.message });
  }
});

// POST /api/trade/close
app.post('/api/trade/close', async (req, res) => {
  try {
    const { tradeId, exitPrice, exitReason } = req.body;
    
    if (!tradeId) return res.status(400).json({ error: 'Trade ID required' });
    if (!exitPrice || exitPrice <= 0) return res.status(400).json({ error: 'Exit price must be > 0' });
    
    // Find the trade in Open Positions
    const openRows = await getSheetData('Open Positions!A2:T');
    let tradeIdx = -1;
    let trade = null;
    
    for (let i = 0; i < openRows.length; i++) {
      if (openRows[i][0] === tradeId) {
        tradeIdx = i;
        trade = openRows[i];
        break;
      }
    }
    
    if (!trade) return res.status(404).json({ error: `Trade ${tradeId} not found` });
    
    const ticker = trade[1];
    const company = trade[2];
    const direction = trade[3];
    const entryDate = trade[4];
    const entryPrice = parseFloat(trade[5]);
    const shares = parseInt(trade[6]);
    const stopLoss = trade[11];
    const takeProfit = trade[12];
    const thesis = trade[15];
    const source = trade[16];
    const insiderName = trade[17];
    const insiderRole = trade[18];
    const filingUrl = trade[19];
    
    // Calculate PnL
    let realizedPnl;
    if (direction === 'LONG') {
      realizedPnl = (exitPrice - entryPrice) * shares;
    } else {
      realizedPnl = (entryPrice - exitPrice) * shares;
    }
    const realizedPct = ((realizedPnl / (entryPrice * shares)) * 100);
    
    // Days held
    const entry = new Date(entryDate);
    const now = new Date();
    const daysHeld = Math.floor((now - entry) / (1000 * 60 * 60 * 24));
    
    const exitDate = formatDate(now);
    
    // Append to Closed Trades
    // Trade ID, Ticker, Company, Direction, Entry Date, Entry Price, Exit Date, Exit Price, Shares, Realized PnL, Realized %, Exit Reason, Days Held, Stop Loss, Take Profit, Thesis, Source, Insider Name, Insider Role, Filing URL
    await appendRow('Closed Trades!A:T', [
      tradeId,
      ticker,
      company,
      direction,
      entryDate,
      entryPrice,
      exitDate,
      exitPrice,
      shares,
      realizedPnl.toFixed(2),
      realizedPct.toFixed(2),
      exitReason || 'manual',
      daysHeld,
      stopLoss,
      takeProfit,
      thesis,
      source,
      insiderName,
      insiderRole,
      filingUrl,
    ]);
    
    // Delete from Open Positions (row index is tradeIdx + 1 for header)
    await deleteRow('Open Positions', tradeIdx + 1);
    
    // Log to Trade Log
    await appendRow('Trade Log!A:E', [
      formatTimestamp(),
      tradeId,
      'CLOSE',
      ticker,
      `${exitReason || 'manual'} | Exit @ $${exitPrice} | PnL: $${realizedPnl.toFixed(2)} (${realizedPct.toFixed(2)}%) | ${daysHeld}d`,
    ]);
    
    // Update portfolio history
    await calculateAndUpdatePortfolio();
    
    res.json({
      success: true,
      realizedPnl,
      message: `Closed ${ticker}: ${realizedPnl >= 0 ? '+' : ''}$${realizedPnl.toFixed(2)} (${realizedPct >= 0 ? '+' : ''}${realizedPct.toFixed(2)}%)`,
    });
  } catch (err) {
    console.error('POST /api/trade/close error:', err.message);
    res.status(400).json({ error: err.message });
  }
});

// POST /api/trade/edit
app.post('/api/trade/edit', async (req, res) => {
  try {
    const { tradeId, stopLoss, takeProfit, trailingStopPct, expirationDate } = req.body;
    
    if (!tradeId) return res.status(400).json({ error: 'Trade ID required' });
    
    // Find the trade
    const openRows = await getSheetData('Open Positions!A2:T');
    let tradeIdx = -1;
    let trade = null;
    
    for (let i = 0; i < openRows.length; i++) {
      if (openRows[i][0] === tradeId) {
        tradeIdx = i;
        trade = [...openRows[i]];
        break;
      }
    }
    
    if (!trade) return res.status(404).json({ error: `Trade ${tradeId} not found` });
    
    // Update fields
    const changes = [];
    if (stopLoss !== undefined && stopLoss !== null) {
      trade[11] = parseFloat(stopLoss).toFixed(2);
      changes.push(`SL: $${trade[11]}`);
    }
    if (takeProfit !== undefined && takeProfit !== null) {
      trade[12] = parseFloat(takeProfit).toFixed(2);
      changes.push(`TP: $${trade[12]}`);
    }
    if (trailingStopPct !== undefined && trailingStopPct !== null) {
      trade[13] = trailingStopPct;
      changes.push(`Trail: ${trailingStopPct}%`);
    }
    if (expirationDate !== undefined && expirationDate !== null) {
      trade[14] = expirationDate;
      changes.push(`Exp: ${expirationDate}`);
    }
    
    // Pad trade array to 20 elements
    while (trade.length < 20) trade.push('');
    
    // Update the row
    const rowNum = tradeIdx + 2; // +1 for header, +1 for 1-indexed
    await updateRow(`Open Positions!A${rowNum}:T${rowNum}`, trade);
    
    // Log
    await appendRow('Trade Log!A:E', [
      formatTimestamp(),
      tradeId,
      'EDIT',
      trade[1],
      changes.join(' | '),
    ]);
    
    res.json({ success: true, message: `Updated ${trade[1]}: ${changes.join(', ')}` });
  } catch (err) {
    console.error('POST /api/trade/edit error:', err.message);
    res.status(400).json({ error: err.message });
  }
});

// --- Start server ---
const PORT = 3000;

initSheets().then(() => {
  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Insider Trade Tracker running on port ${PORT}`);
  });
}).catch(err => {
  console.error('Failed to initialize Google Sheets:', err.message);
  // Start anyway so frontend loads, API calls will fail gracefully
  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Server running on port ${PORT} (Sheets not connected)`);
  });
});
