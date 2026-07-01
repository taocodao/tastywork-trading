#!/usr/bin/env python3
"""
SNDK Bot — Live Log Viewer & Health API
========================================
Lightweight HTTP server that exposes:
  GET /sndk/logs       — HTML page with auto-refreshing log viewer
  GET /sndk/status     — JSON health check
  GET /sndk/trades     — JSON trade history
  GET /sndk/positions  — JSON current positions
  GET /sndk/api/logs   — JSON raw log tail (for AJAX)
"""
import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from pathlib import Path
from datetime import datetime

PORT = 8005
LOG_FILE = Path("logs/sndk_live.log")
TRADE_LOG = Path("data/sndk_trades.jsonl")
STATE_FILE = Path("data/sndk_live_state.json")

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

def _read_log_tail(n=200):
    """Read last N lines from log file, deduplicating the double-log bug."""
    if not LOG_FILE.exists():
        return []
    lines = LOG_FILE.read_text(errors="replace").strip().split("\n")
    tail = lines[-n*2:] if len(lines) > n*2 else lines
    # Deduplicate consecutive identical lines (dual-log bug workaround)
    deduped = []
    prev = None
    for line in tail:
        if line != prev:
            deduped.append(line)
            prev = line
    return deduped[-n:]

def _read_trades():
    if not TRADE_LOG.exists():
        return []
    trades = []
    for line in TRADE_LOG.read_text(errors="replace").strip().split("\n"):
        if line.strip():
            try:
                trades.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return trades

def _read_positions():
    if not STATE_FILE.exists():
        return []
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return []

def _get_service_status():
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "sndk-live"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"

def _get_uptime():
    try:
        result = subprocess.run(
            ["systemctl", "show", "sndk-live", "--property=ActiveEnterTimestamp"],
            capture_output=True, text=True, timeout=5
        )
        ts = result.stdout.strip().split("=", 1)[-1]
        return ts
    except Exception:
        return "unknown"

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SNDK Bot — Live Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0a0e17;
    --surface: #111827;
    --surface2: #1a2332;
    --border: #1e2a3a;
    --accent: #00d4aa;
    --accent2: #6366f1;
    --danger: #ef4444;
    --warn: #f59e0b;
    --text: #e2e8f0;
    --text-dim: #64748b;
    --text-bright: #f8fafc;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Inter', sans-serif;
    min-height: 100vh;
  }
  .header {
    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%);
    border-bottom: 1px solid var(--border);
    padding: 16px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 100;
    backdrop-filter: blur(12px);
  }
  .header h1 {
    font-size: 20px;
    font-weight: 600;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: -0.5px;
  }
  .header-status {
    display: flex;
    align-items: center;
    gap: 16px;
    font-size: 13px;
  }
  .status-badge {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border-radius: 20px;
    font-weight: 500;
    font-size: 12px;
  }
  .status-badge.active {
    background: rgba(0, 212, 170, 0.12);
    color: var(--accent);
    border: 1px solid rgba(0, 212, 170, 0.3);
  }
  .status-badge.inactive {
    background: rgba(239, 68, 68, 0.12);
    color: var(--danger);
    border: 1px solid rgba(239, 68, 68, 0.3);
  }
  .pulse {
    width: 8px; height: 8px;
    border-radius: 50%;
    animation: pulse 2s ease-in-out infinite;
  }
  .pulse.green { background: var(--accent); box-shadow: 0 0 8px var(--accent); }
  .pulse.red { background: var(--danger); box-shadow: 0 0 8px var(--danger); }
  @keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.5; transform: scale(0.85); }
  }

  .tabs {
    display: flex;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 0 24px;
  }
  .tab {
    padding: 12px 20px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
    color: var(--text-dim);
    border-bottom: 2px solid transparent;
    transition: all 0.2s;
  }
  .tab:hover { color: var(--text); }
  .tab.active {
    color: var(--accent);
    border-bottom-color: var(--accent);
  }

  .content { padding: 20px 24px; }
  .panel { display: none; }
  .panel.active { display: block; }

  /* Log viewer */
  .log-container {
    background: #050810;
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
  }
  .log-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 16px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    font-size: 12px;
  }
  .log-toolbar label {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--text-dim);
  }
  .log-toolbar input[type=checkbox] {
    accent-color: var(--accent);
  }
  .log-toolbar select, .log-toolbar input[type=number] {
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 4px 8px;
    border-radius: 6px;
    font-size: 12px;
  }
  .log-body {
    padding: 12px 16px;
    max-height: 70vh;
    overflow-y: auto;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    line-height: 1.7;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .log-body::-webkit-scrollbar { width: 6px; }
  .log-body::-webkit-scrollbar-track { background: transparent; }
  .log-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

  .log-line { padding: 1px 0; }
  .log-line.info { color: var(--text); }
  .log-line.warning { color: var(--warn); }
  .log-line.error { color: var(--danger); font-weight: 500; }
  .log-line.debug { color: var(--text-dim); }
  .log-line .ts { color: var(--text-dim); }
  .log-line .module { color: var(--accent2); }

  /* Stats cards */
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 16px;
    margin-bottom: 20px;
  }
  .stat-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px 20px;
    transition: border-color 0.2s;
  }
  .stat-card:hover { border-color: var(--accent); }
  .stat-card .label {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-dim);
    margin-bottom: 6px;
  }
  .stat-card .value {
    font-size: 24px;
    font-weight: 600;
    color: var(--text-bright);
  }
  .stat-card .value.green { color: var(--accent); }
  .stat-card .value.red { color: var(--danger); }
  .stat-card .value.yellow { color: var(--warn); }

  /* Trades table */
  .trades-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  .trades-table th {
    text-align: left;
    padding: 10px 12px;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-dim);
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
  }
  .trades-table td {
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
  }
  .trades-table tr:hover td { background: var(--surface2); }
  .badge {
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
  }
  .badge.open { background: rgba(0,212,170,0.15); color: var(--accent); }
  .badge.close { background: rgba(99,102,241,0.15); color: var(--accent2); }
  .badge.put { background: rgba(239,68,68,0.12); color: var(--danger); }
  .badge.call { background: rgba(0,212,170,0.12); color: var(--accent); }

  .empty-state {
    text-align: center;
    padding: 60px 20px;
    color: var(--text-dim);
  }
  .empty-state .icon { font-size: 48px; margin-bottom: 12px; }

  @media (max-width: 768px) {
    .header { padding: 12px 16px; }
    .content { padding: 12px 16px; }
    .stats-grid { grid-template-columns: repeat(2, 1fr); }
  }
</style>
</head>
<body>

<div class="header">
  <h1>⚡ SNDK Options Bot</h1>
  <div class="header-status">
    <div class="status-badge" id="statusBadge">
      <div class="pulse" id="statusPulse"></div>
      <span id="statusText">Loading...</span>
    </div>
    <span style="color: var(--text-dim); font-size: 12px;" id="uptimeText"></span>
  </div>
</div>

<div class="tabs">
  <div class="tab active" data-tab="logs">📋 Live Logs</div>
  <div class="tab" data-tab="trades">💹 Trades</div>
  <div class="tab" data-tab="positions">📊 Positions</div>
</div>

<div class="content">
  <!-- LOGS PANEL -->
  <div class="panel active" id="panel-logs">
    <div class="stats-grid" id="statsGrid"></div>
    <div class="log-container">
      <div class="log-toolbar">
        <div style="display:flex;gap:16px;align-items:center">
          <label><input type="checkbox" id="autoScroll" checked> Auto-scroll</label>
          <label>Filter:
            <select id="logFilter">
              <option value="all">All</option>
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="error">Error</option>
              <option value="signal">Signals Only</option>
            </select>
          </label>
          <label>Lines: <input type="number" id="lineCount" value="150" min="20" max="500" style="width:60px"></label>
        </div>
        <div style="color:var(--text-dim)">
          Refreshing every <span id="refreshInterval">3</span>s
        </div>
      </div>
      <div class="log-body" id="logBody">Loading...</div>
    </div>
  </div>

  <!-- TRADES PANEL -->
  <div class="panel" id="panel-trades">
    <div id="tradesContent"></div>
  </div>

  <!-- POSITIONS PANEL -->
  <div class="panel" id="panel-positions">
    <div id="positionsContent"></div>
  </div>
</div>

<script>
  // Tab switching
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById('panel-' + tab.dataset.tab).classList.add('active');
    });
  });

  function classifyLine(line) {
    const lower = line.toLowerCase();
    if (lower.includes('error') || lower.includes('traceback') || lower.includes('exception'))
      return 'error';
    if (lower.includes('warning') || lower.includes('kill switch') || lower.includes('risk limit'))
      return 'warning';
    if (lower.includes('debug'))
      return 'debug';
    return 'info';
  }

  function formatLogLine(line) {
    const cls = classifyLine(line);
    // Highlight timestamp and module
    let formatted = line
      .replace(/^(\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2},\\d{3})/, '<span class="ts">$1</span>')
      .replace(/( - )(\\S+)( - )/, '$1<span class="module">$2</span>$3');
    return `<div class="log-line ${cls}">${formatted}</div>`;
  }

  function filterLines(lines, filter) {
    if (filter === 'all') return lines;
    return lines.filter(l => {
      const lower = l.toLowerCase();
      if (filter === 'signal') return lower.includes('signal') || lower.includes('entry') || lower.includes('regime') || lower.includes('trade');
      return classifyLine(l) === filter;
    });
  }

  async function fetchLogs() {
    const n = document.getElementById('lineCount').value || 150;
    try {
      const res = await fetch('/sndk/api/logs?n=' + n);
      const data = await res.json();
      const filter = document.getElementById('logFilter').value;
      const filtered = filterLines(data.lines, filter);
      const logBody = document.getElementById('logBody');
      logBody.innerHTML = filtered.map(formatLogLine).join('');
      if (document.getElementById('autoScroll').checked) {
        logBody.scrollTop = logBody.scrollHeight;
      }
    } catch (e) {
      document.getElementById('logBody').innerHTML = '<div class="log-line error">Failed to fetch logs: ' + e.message + '</div>';
    }
  }

  async function fetchStatus() {
    try {
      const res = await fetch('/sndk/status');
      const data = await res.json();
      const badge = document.getElementById('statusBadge');
      const pulse = document.getElementById('statusPulse');
      const text = document.getElementById('statusText');
      const uptime = document.getElementById('uptimeText');

      const isActive = data.service_status === 'active';
      badge.className = 'status-badge ' + (isActive ? 'active' : 'inactive');
      pulse.className = 'pulse ' + (isActive ? 'green' : 'red');
      text.textContent = isActive ? 'Running' : data.service_status;
      uptime.textContent = data.uptime ? 'Since ' + data.uptime : '';

      // Stats cards
      const grid = document.getElementById('statsGrid');
      
      let ddsClass = 'yellow';
      if (data.dds_state === 'FLAT') ddsClass = '';
      else if (data.dds_state === 'BALANCED') ddsClass = 'green';
      else if (data.dds_state === 'ONE_SIDED') ddsClass = 'red';
      
      grid.innerHTML = `
        <div class="stat-card">
          <div class="label">DDS State</div>
          <div class="value ${ddsClass}">${data.dds_state || 'UNKNOWN'}</div>
        </div>
        <div class="stat-card">
          <div class="label">DSS Score</div>
          <div class="value ${(data.dss_score || 0) > 0 ? 'green' : 'red'}">${data.dss_score != null ? data.dss_score.toFixed(2) : '0.00'}</div>
        </div>
        <div class="stat-card">
          <div class="label">Margin Health</div>
          <div class="value ${data.margin_health === 'OK' ? 'green' : 'red'}">${data.margin_health || 'OK'}</div>
        </div>
        <div class="stat-card">
          <div class="label">Regime</div>
          <div class="value ${data.regime === 'EXTREME_UPTREND' ? 'green' : data.regime === 'EXTREME_DOWNTREND' ? 'red' : 'yellow'}">${data.regime || 'N/A'}</div>
        </div>
        <div class="stat-card">
          <div class="label">Open P/C</div>
          <div class="value">${data.open_puts || 0} / ${data.open_calls || 0}</div>
        </div>
      `;
    } catch(e) { console.error('Status fetch failed:', e); }
  }

  async function fetchTrades() {
    try {
      const res = await fetch('/sndk/trades');
      const trades = await res.json();
      const container = document.getElementById('tradesContent');
      if (!trades.length) {
        container.innerHTML = '<div class="empty-state"><div class="icon">📭</div><p>No trades recorded yet.</p><p style="margin-top:8px;font-size:13px">The bot is waiting for a signal to fire.</p></div>';
        return;
      }
      let html = '<table class="trades-table"><thead><tr><th>Time</th><th>Action</th><th>Type</th><th>Strike</th><th>Expiry</th><th>Qty</th><th>Price</th><th>P&L</th><th>Reason</th></tr></thead><tbody>';
      trades.reverse().forEach(t => {
        const pnl = t.realized_pnl ? (t.realized_pnl > 0 ? '+' : '') + t.realized_pnl.toFixed(2) : '—';
        const pnlClass = t.realized_pnl > 0 ? 'green' : t.realized_pnl < 0 ? 'red' : '';
        html += `<tr>
          <td>${new Date(t.timestamp).toLocaleString()}</td>
          <td><span class="badge ${t.action.toLowerCase()}">${t.action}</span></td>
          <td><span class="badge ${t.type}">${t.type.toUpperCase()}</span></td>
          <td>$${t.strike}</td>
          <td>${t.expiry}</td>
          <td>${t.contracts}</td>
          <td>$${t.price.toFixed(2)}</td>
          <td style="color:var(--${pnlClass || 'text-dim'})">${pnl}</td>
          <td>${t.reason || '—'}</td>
        </tr>`;
      });
      html += '</tbody></table>';
      container.innerHTML = html;
    } catch(e) {
      document.getElementById('tradesContent').innerHTML = '<div class="empty-state error">Failed to load trades</div>';
    }
  }

  async function fetchPositions() {
    try {
      const res = await fetch('/sndk/positions');
      const positions = await res.json();
      const container = document.getElementById('positionsContent');
      if (!positions.length) {
        container.innerHTML = '<div class="empty-state"><div class="icon">📋</div><p>No open positions.</p></div>';
        return;
      }
      let html = '<table class="trades-table"><thead><tr><th>Symbol</th><th>Type</th><th>Strike</th><th>Expiry</th><th>Entry Δ</th><th>Entry IV</th><th>Premium</th><th>Qty</th><th>DTE Target</th><th>Opened</th></tr></thead><tbody>';
      positions.forEach(p => {
        html += `<tr>
          <td>${p.symbol}</td>
          <td><span class="badge ${p.opt_type}">${p.opt_type.toUpperCase()}</span></td>
          <td>$${p.strike}</td>
          <td>${p.expiry}</td>
          <td>${(p.entry_delta).toFixed(3)}</td>
          <td>${(p.entry_iv * 100).toFixed(1)}%</td>
          <td>$${p.entry_premium.toFixed(2)}</td>
          <td>${p.contracts}</td>
          <td>${p.target_dte}d</td>
          <td>${new Date(p.entry_date).toLocaleString()}</td>
        </tr>`;
      });
      html += '</tbody></table>';
      container.innerHTML = html;
    } catch(e) {
      document.getElementById('positionsContent').innerHTML = '<div class="empty-state error">Failed to load positions</div>';
    }
  }

  // Initial load
  fetchLogs();
  fetchStatus();
  fetchTrades();
  fetchPositions();

  // Auto-refresh
  setInterval(fetchLogs, 3000);
  setInterval(fetchStatus, 10000);
  setInterval(fetchTrades, 15000);
  setInterval(fetchPositions, 15000);
</script>
</body>
</html>"""


class SNDKLogHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress HTTP access logs

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _send_html(self, html, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def do_GET(self):
        path = self.path.split("?")[0]
        params = {}
        if "?" in self.path:
            for kv in self.path.split("?")[1].split("&"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    params[k] = v

        if path == "/sndk/logs" or path == "/sndk/" or path == "/sndk":
            self._send_html(HTML_PAGE)

        elif path == "/sndk/api/logs":
            n = int(params.get("n", 150))
            lines = _read_log_tail(n)
            self._send_json({"lines": lines, "count": len(lines)})

        elif path == "/sndk/status":
            service_status = _get_service_status()
            uptime = _get_uptime()
            positions = _read_positions()
            trades = _read_trades()
            log_lines = 0
            if LOG_FILE.exists():
                log_lines = sum(1 for _ in open(LOG_FILE, errors="replace"))

            # Parse regime/IVR/DDS from last log lines
            regime = "N/A"
            ivr = None
            dss_score = 0.0
            margin_health = "OK"
            
            for line in reversed(_read_log_tail(150)):
                if "Regime Refreshed:" in line:
                    parts = line.split("Regime Refreshed:")[-1].strip()
                    if "," in parts:
                        regime = parts.split(",")[0].strip()
                        try:
                            ivr = float(parts.split("IVR")[-1].strip())
                        except ValueError:
                            pass
                elif "DDS Evaluation - State:" in line:
                    try:
                        score_str = line.split("Score:")[-1].strip()
                        dss_score = float(score_str)
                    except:
                        pass
                elif "Margin health" in line:
                    try:
                        # Extract OK, CAUTION, WARNING, CRITICAL
                        margin_health = line.split("Margin health")[1].strip().split()[0]
                    except:
                        pass
                        
            open_puts = sum(p.get("contracts", 1) for p in positions if p.get("opt_type") == "put")
            open_calls = sum(p.get("contracts", 1) for p in positions if p.get("opt_type") == "call")
            
            if open_calls == 0 and open_puts == 0:
                dds_state = "FLAT"
            elif open_calls > open_puts and open_puts == 0:
                dds_state = "ONE_SIDED"
            elif open_puts > open_calls and open_calls == 0:
                dds_state = "ONE_SIDED"
            elif open_calls > open_puts:
                dds_state = "CALL_HEAVY"
            elif open_puts > open_calls:
                dds_state = "PUT_HEAVY"
            else:
                dds_state = "BALANCED"

            self._send_json({
                "service_status": service_status,
                "uptime": uptime,
                "regime": regime,
                "ivr": ivr,
                "dds_state": dds_state,
                "dss_score": dss_score,
                "margin_health": margin_health,
                "open_puts": open_puts,
                "open_calls": open_calls,
                "open_positions": len(positions),
                "total_trades": len(trades),
                "log_lines": log_lines,
                "timestamp": datetime.now().isoformat()
            })

        elif path == "/sndk/trades":
            self._send_json(_read_trades())

        elif path == "/sndk/positions":
            self._send_json(_read_positions())

        elif path == "/sndk/dds":
            # Endpoint for the DDS Dashboard Card external monitoring
            positions = _read_positions()
            open_puts = sum(p.get("contracts", 1) for p in positions if p.get("opt_type") == "put")
            open_calls = sum(p.get("contracts", 1) for p in positions if p.get("opt_type") == "call")
            
            if open_calls == 0 and open_puts == 0:
                dds_state = "FLAT"
            elif open_calls > open_puts and open_puts == 0:
                dds_state = "ONE_SIDED"
            elif open_puts > open_calls and open_calls == 0:
                dds_state = "ONE_SIDED"
            elif open_calls > open_puts:
                dds_state = "CALL_HEAVY"
            elif open_puts > open_calls:
                dds_state = "PUT_HEAVY"
            else:
                dds_state = "BALANCED"
                
            dss_score = 0.0
            margin_health = "OK"
            
            for line in reversed(_read_log_tail(150)):
                if "DDS Evaluation - State:" in line:
                    try:
                        score_str = line.split("Score:")[-1].strip()
                        dss_score = float(score_str)
                    except:
                        pass
                elif "Margin health" in line:
                    try:
                        margin_health = line.split("Margin health")[1].strip().split()[0]
                    except:
                        pass
                        
            self._send_json({
                "dds_state": dds_state,
                "dss_score": dss_score,
                "open_puts": open_puts,
                "open_calls": open_calls,
                "margin_health": margin_health
            })

        else:
            self._send_json({"error": "Not found", "endpoints": ["/sndk/logs", "/sndk/status", "/sndk/trades", "/sndk/positions", "/sndk/dds"]}, 404)


if __name__ == "__main__":
    print(f"[SNDK] Log Viewer starting on port {PORT}")
    print(f"   Dashboard: http://localhost:{PORT}/sndk/logs")
    print(f"   Status:    http://localhost:{PORT}/sndk/status")
    print(f"   Trades:    http://localhost:{PORT}/sndk/trades")
    print(f"   Positions: http://localhost:{PORT}/sndk/positions")
    server = ThreadedHTTPServer(("0.0.0.0", PORT), SNDKLogHandler)
    server.serve_forever()
